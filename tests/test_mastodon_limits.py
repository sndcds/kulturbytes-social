import os
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
from kulturbytes_common.events import build_hashtags, get_event_url
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
        self.assertEqual(mastodon.build_mastodon_message(EVENT),
                         '📅 Kulturabend\n🗓 01.01.2099 · 18:30 Uhr\n📍 Kulturhaus, Flensburg\n\n'
                         'Musik und Kultur.\n\nEintritt frei\n'
                         '👉 https://kulturbytes.de/de/veranstaltung/event-1/209901011830\n'
                         '#Kultur #SchleswigHolstein #Kulturbytes #Flensburg')

    def test_summary_boundaries_and_complete_footer(self):
        event = deepcopy(EVENT)
        event['summary'] = 'Überraschung Musik 🎵 Kultur ' * 100
        for limit in [250, 500, 750]:
            with self.subTest(limit=limit):
                message = mastodon.build_mastodon_message(event, limit)
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
        required_length = len(mastodon.build_mastodon_message(fixed))
        message = mastodon.build_mastodon_message(event, required_length)
        self.assertEqual(message, mastodon.build_mastodon_message(fixed))
        message = mastodon.build_mastodon_message(event, required_length + len('Untertitel') + 1)
        self.assertIn('Untertitel', message)
        self.assertNotIn('Eintritt frei', message)
        self.assertNotIn('https://example.test', message)
        self.assertNotIn('Veranstalter:', message)
        message = mastodon.build_mastodon_message(event, 750)
        self.assertIn(event['date']['ticket_link'], message)
        self.assertIn('Veranstalter: Veranstalter', message)

    def test_exact_required_boundary_and_oversized_hashtags(self):
        event = deepcopy(EVENT)
        event['summary'] = ''
        event['date'].pop('price_type')
        fixed = mastodon.build_mastodon_message(event)
        self.assertEqual(mastodon.build_mastodon_message(event, len(fixed)), fixed)
        with self.assertRaises(click.ClickException):
            mastodon.build_mastodon_message(event, len(fixed) - 1)
        event['tags'] = ['SehrLangerHashtag' * 100]
        with self.assertRaises(click.ClickException):
            mastodon.build_mastodon_message(event, 500)
