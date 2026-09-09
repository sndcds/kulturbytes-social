from canonical_support import canonical
import os
import sqlite3
import tempfile
import unittest
from dotenv_support import IsolatedEnvironmentTestCase
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

import click
import httpx
from click.testing import CliRunner
from kulturbytes_social.cli import cli

from kulturbytes_common.sources.kulturbytes_api import build_hashtags, get_event_url
from test_publishers import EVENT, SUMMARY, MASTODON as mastodon, ENV


class MastodonLimitTests(IsolatedEnvironmentTestCase):
    def test_instance_limit_and_fallback(self):
        payloads = [({'configuration': {'statuses': {'max_characters': 750}}}, 750),
                    ({'configuration': {'statuses': {'max_characters': 500}}}, 500)]
        for value in [None, 0, -1, True, '750', 750.5, [], {}]:
            payloads.append(({'configuration': {'statuses': {'max_characters': value}}}, 500))
        payloads += [(value, 500) for value in [None, [], {}, {'configuration': None},
                                              {'configuration': {'statuses': []}}]]
        responses = [(httpx.Response(200, json=payload), expected) for payload, expected in payloads]
        responses += [(httpx.Response(500), 500), (httpx.Response(200, text='invalid'), 500),
                      (httpx.ReadTimeout('timeout'), 500), (httpx.Response(401), 500)]
        for response, expected in responses:
            with self.subTest(response=response, expected=expected):
                requests = []

                def respond(request):
                    requests.append(request)
                    self.assertEqual(str(request.url), 'https://example.test/api/v2/instance')
                    self.assertEqual(request.method, 'GET')
                    self.assertNotIn('Authorization', request.headers)
                    if isinstance(response, Exception):
                        raise response
                    return response

                with httpx.Client(transport=httpx.MockTransport(respond)) as client, patch.object(click, 'echo'):
                    self.assertEqual(mastodon.get_status_limit(client, 'https://example.test'), expected)
                self.assertEqual(len(requests), 3 if isinstance(response, httpx.ReadTimeout) else 1)

    def test_short_message_unchanged(self):
        self.assertEqual(mastodon.build_mastodon_message(canonical(EVENT)),
                         '📅 Kulturabend\n🗓 01.01.2099 · 18:30 Uhr\n📍 Kulturhaus, Flensburg\n\n'
                         'Musik und Kultur.\n\nEintritt frei\n'
                         '👉 https://kulturbytes.de/de/veranstaltung/event-1/209901011830\n'
                         '#Kultur #SchleswigHolstein #Kulturbytes #Flensburg')

    def test_summary_boundaries_and_complete_footer(self):
        event = deepcopy(EVENT)
        event['summary'] = 'Überraschung Musik 🎵 Kultur ' * 100
        for limit in [250, 500, 750]:
            with self.subTest(limit=limit):
                message = mastodon.build_mastodon_message(canonical(event), limit)
                self.assertLessEqual(len(message), limit)
                self.assertIn(get_event_url(event), message)
                self.assertTrue(message.endswith(build_hashtags(event)))
                summary = message.split('\n\n')[1]
                self.assertTrue(summary.endswith('…'))
                self.assertIn(summary[:-1].split()[-1], event['summary'].split())
        self.assertEqual(mastodon.trim_summary('abcdefghijk', 5), '')
        self.assertEqual(mastodon.trim_summary('Hallo Welt', 6), 'Hallo…')
        self.assertEqual(mastodon.trim_summary('Hallo\nWelt', 10), 'Hallo\nWelt')

    def test_optional_metadata_dropped_whole_in_priority_order(self):
        event = deepcopy(EVENT)
        event.update(summary='', subtitle='Untertitel', org_name='Veranstalter')
        event['date']['ticket_link'] = 'https://example.test/tickets'
        fixed = deepcopy(event)
        fixed.pop('subtitle')
        fixed.pop('org_name')
        fixed['date'].pop('ticket_link')
        fixed['date'].pop('price_type')
        required_length = len(mastodon.build_mastodon_message(canonical(fixed)))
        message = mastodon.build_mastodon_message(canonical(event), required_length)
        self.assertEqual(message, mastodon.build_mastodon_message(canonical(fixed)))
        message = mastodon.build_mastodon_message(canonical(event), required_length + len('Untertitel') + 1)
        self.assertIn('Untertitel', message)
        self.assertNotIn('Eintritt frei', message)
        self.assertNotIn('https://example.test', message)
        self.assertNotIn('Veranstalter:', message)
        message = mastodon.build_mastodon_message(canonical(event), 750)
        self.assertIn(event['date']['ticket_link'], message)
        self.assertIn('Veranstalter: Veranstalter', message)

    def run_cli(self, directory, details, limit, args, user_input):
        requests = []
        summaries = [dict(SUMMARY, date_uuid=e['date']['uuid'], date_slug=e['date']['slug'],
                          summary=e.get('summary', '')) for e in details]
        by_path = {f"/api/event/event-1/date/{e['date']['slug']}": e for e in details}

        def respond(request):
            requests.append(request)
            path = request.url.path
            if path == '/api/events':
                return httpx.Response(200, json={'data': {'events': summaries}})
            if path in by_path:
                return httpx.Response(200, json={'data': by_path[path]})
            if path == '/api/v2/instance':
                self.assertNotIn('Authorization', request.headers)
                return httpx.Response(200, json={'configuration': {'statuses': {'max_characters': limit}}})
            self.assertEqual(path, '/api/v1/statuses')
            self.assertEqual(request.method, 'POST')
            return httpx.Response(200, json={'id': f'post-{len(requests)}'})

        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.dict(os.environ, ENV, clear=True), patch.object(
            mastodon, 'DATABASE_PATH', Path(directory) / 'posts.sqlite3',
        ), patch('kulturbytes_common.workflow.httpx.Client', return_value=client):
            result = CliRunner().invoke(cli, ['mastodon'] + args, input=user_input)
        return result, requests

    def test_once_per_run_and_preview_matches_actual_status(self):
        events = [deepcopy(EVENT), deepcopy(EVENT)]
        events[1]['date'].update(uuid='date-2', slug='second-date')
        for event in events:
            event['summary'] = 'Kultur und Überraschungen ' * 100
        for limit in [500, 750, None]:
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as directory:
                with patch.object(mastodon, 'render_post', wraps=mastodon.render_post) as build:
                    result, requests = self.run_cli(directory, events, limit, ['--publish'], 'all\ny\ny\n')
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(build.call_count, 2)
                self.assertEqual(sum(r.url.path == '/api/v2/instance' for r in requests), 1)
                posted = [parse_qs(r.content.decode())['status'][0] for r in requests if r.method == 'POST']
                self.assertEqual(len(posted), 2)
                for message in posted:
                    self.assertIn(message, result.output)
                    self.assertIn(f'Zeichen: {len(message)}/{limit or 500}', result.output)
                    self.assertLessEqual(len(message), limit or 500)
                with sqlite3.connect(Path(directory) / 'posts.sqlite3') as conn:
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM published_events').fetchone(), (2,))

    def test_exact_required_boundary_and_oversized_hashtags(self):
        event = deepcopy(EVENT)
        event['summary'] = ''
        event['date'].pop('price_type')
        fixed = mastodon.build_mastodon_message(canonical(event))
        self.assertEqual(mastodon.build_mastodon_message(canonical(event), len(fixed)), fixed)
        with self.assertRaises(click.ClickException):
            mastodon.build_mastodon_message(canonical(event), len(fixed) - 1)
        event['tags'] = ['SehrLangerHashtag' * 100]
        with self.assertRaises(click.ClickException):
            mastodon.build_mastodon_message(canonical(event), 500)

    def test_real_metadata_discovery_in_credential_free_dry_run(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(ENV, {}, clear=True):
            event = deepcopy(EVENT)
            event['summary'] = 'Lange Beschreibung mit Kultur ' * 100
            result, requests = self.run_cli(directory, [event], 750, ['--dry-run'], '1\n')
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn('DRY RUN', result.output)
            self.assertIn('/750', result.output)
            self.assertEqual(sum(r.url.path == '/api/v2/instance' for r in requests), 1)
            self.assertTrue(all(r.method == 'GET' for r in requests))
            with sqlite3.connect(Path(directory) / 'posts.sqlite3') as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM published_events').fetchone(), (0,))

    def test_required_overflow_does_not_publish_or_change_database(self):
        for dry_run in [False, True]:
            with self.subTest(dry_run=dry_run), tempfile.TemporaryDirectory() as directory:
                database = Path(directory) / 'posts.sqlite3'
                with patch.object(mastodon, 'DATABASE_PATH', database):
                    conn = mastodon.init_database()
                    mastodon.remember_post(conn, EVENT, 'old-post', 'https://example.test/old')
                    before = conn.execute('SELECT * FROM published_events').fetchall()
                    conn.close()
                event = deepcopy(EVENT)
                event['title'] = 'Langer Titel ' * 100
                event['images'] = {'main': {'url': 'https://example.test/image.jpg'}}
                args = ['--event-uuid', 'event-1', '--date-identifier', 'date-1', '--include-published',
                        '--dry-run' if dry_run else '--publish']
                result, requests = self.run_cli(directory, [event], 500, args, 'y\ny\n')
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertIn('Instanzlimit von 500 Zeichen', result.output)
                self.assertFalse(any(r.method == 'POST' for r in requests))
                self.assertFalse(any(r.url.host == 'example.test' for r in requests))
                with sqlite3.connect(database) as conn:
                    self.assertEqual(conn.execute('SELECT * FROM published_events').fetchall(), before)


if __name__ == '__main__':
    unittest.main()
