import importlib
import os
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import click
import httpx
from click.testing import CliRunner
from kulturbytes_social.cli import cli

from kulturbytes_common.database import already_published
from kulturbytes_common.events import build_address, build_hashtags, format_price
from kulturbytes_common.media import download_image
from kulturbytes_common.selection import parse_selection

ENV = {
    'FACEBOOK_PAGE_ID': '123',
    'FACEBOOK_PAGE_ACCESS_TOKEN': 'test-facebook-token',
    'MASTODON_ACCESS_TOKEN': 'test-mastodon-token',
}
FACEBOOK = importlib.import_module('kulturbytes_facebook.cli')
MASTODON = importlib.import_module('kulturbytes_mastodon.cli')

EVENT = {
    'uuid': 'event-1', 'title': 'Kulturabend', 'summary': 'Musik und Kultur.',
    'tags': ['Kultur', 'kultur', 'Schleswig-Holstein'],
    'date': {
        'uuid': 'date-1', 'slug': '209901011830', 'start_date': '2099-01-01',
        'start_time': '18:30', 'venue_name': 'Kulturhaus', 'venue_city': 'Flensburg',
        'venue_street': 'Hauptstraße', 'venue_house_number': '1',
        'venue_postal_code': '24937', 'price_type': 'free',
    },
}
SUMMARY = {
    'uuid': 'event-1', 'date_uuid': 'date-1', 'date_slug': '209901011830',
    'release_status': 'released', 'start_date': '2099-01-01',
    'start_time': '18:30', 'title': 'Kulturabend', 'venue_city': 'Flensburg',
}


class SharedFunctionsTests(unittest.TestCase):
    def test_selection(self):
        self.assertEqual(parse_selection('1,3-5,3', 5), [0, 2, 3, 4])
        self.assertEqual(parse_selection('alle', 3), [0, 1, 2])
        self.assertEqual(parse_selection('', 3), [])
        for value in ['0', '4', '2-1', 'abc']:
            with self.subTest(value=value), self.assertRaises(click.ClickException):
                parse_selection(value, 3)

    def test_formatting(self):
        self.assertEqual(build_address(EVENT), 'Hauptstraße 1, 24937 Flensburg')
        self.assertEqual(build_hashtags(EVENT), '#Kultur #SchleswigHolstein #Kulturbytes #Flensburg')
        self.assertEqual(format_price(EVENT), 'Eintritt frei')

    def test_image_download(self):
        event = deepcopy(EVENT)
        event['images'] = {'main': {'url': 'https://example.test/image', 'uuid': 'image-1'}}
        with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b'image', headers={'Content-Type': 'image/png; charset=binary'})
        )) as client:
            self.assertEqual(download_image(client, event), (b'image', 'image/png', 'image-1.png'))
            with self.assertRaises(ValueError):
                download_image(client, EVENT)


class PublisherTests(unittest.TestCase):
    def run_cli(self, module, directory, args, user_input, summaries=None, expected_exit=0):
        requests = []

        def respond(request):
            requests.append(request)
            self.assertEqual(request.method, 'GET')
            if request.url.path == '/api/events':
                return httpx.Response(200, json={'data': {'events': summaries if summaries is not None else [SUMMARY]}})
            self.assertEqual(request.url.path, '/api/event/event-1/date/209901011830')
            return httpx.Response(200, json={'data': EVENT})
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(MASTODON, 'get_status_limit', return_value=500), patch.dict(os.environ, ENV, clear=True), patch.object(module, 'DATABASE_PATH', Path(directory) / 'posts.sqlite3'), patch(
            'kulturbytes_common.workflow.httpx.Client', return_value=client
        ):
            result = CliRunner().invoke(cli, [module.__name__.split('.')[0].removeprefix('kulturbytes_')] + args, input=user_input)
        self.assertEqual(result.exit_code, expected_exit, result.output + str(result.exception))
        return result, requests

    def test_dry_run_for_both_platforms(self):
        for module in [FACEBOOK, MASTODON]:
            with self.subTest(platform=module.__name__), tempfile.TemporaryDirectory() as directory:
                result, requests = self.run_cli(module, directory, ['--dry-run'], '1\n')
                self.assertIn('DRY RUN', result.output)
                self.assertIn('Kulturabend', result.output)
                self.assertEqual(len(requests), 2)
                with sqlite3.connect(Path(directory) / 'posts.sqlite3') as conn:
                    self.assertFalse(already_published(conn, 'date-1'))

    def test_social_text_uses_list_summary_or_detail_description(self):
        detail = dict(EVENT, summary='Detail summary must not be used.',
                      description='Description from the detail response.')
        for module in [FACEBOOK, MASTODON]:
            for summary in ['Summary from the event list.', None, '', '   ']:
                with self.subTest(platform=module.__name__, summary=summary), tempfile.TemporaryDirectory() as directory:
                    listed = dict(SUMMARY)
                    if summary is not None:
                        listed['summary'] = summary
                    with patch.dict(EVENT, detail):
                        result, requests = self.run_cli(
                            module, directory, ['--dry-run'], '1\n', [listed],
                        )
                    expected = summary if summary and summary.strip() else detail['description']
                    self.assertIn(expected, result.output)
                    self.assertNotIn(detail['summary'], result.output)
                    if summary and summary.strip():
                        self.assertNotIn(detail['description'], result.output)
                    self.assertEqual(len(requests), 2)
                    with sqlite3.connect(Path(directory) / 'posts.sqlite3') as conn:
                        self.assertFalse(already_published(conn, 'date-1'))

    def test_publish_requires_confirmation(self):
        for module in [FACEBOOK, MASTODON]:
            with self.subTest(platform=module.__name__), tempfile.TemporaryDirectory() as directory:
                result, _ = self.run_cli(module, directory, ['--publish'], '1\nn\n')
                self.assertIn('Übersprungen.', result.output)

    def test_existing_database_and_duplicate_filter(self):
        for module in [FACEBOOK, MASTODON]:
            with self.subTest(platform=module.__name__), tempfile.TemporaryDirectory() as directory:
                with patch.object(module, 'DATABASE_PATH', Path(directory) / 'posts.sqlite3'):
                    conn = module.init_database()
                    if module is FACEBOOK:
                        module.remember_post(conn, EVENT, 'post-1')
                    else:
                        module.remember_post(conn, EVENT, 'post-1', 'https://example.test/post-1')
                    self.assertTrue(already_published(conn, 'date-1'))
                    conn.close()
                result, requests = self.run_cli(module, directory, [], '')
                self.assertIn('0 Termine stehen zur Auswahl.', result.output)
                self.assertEqual(len(requests), 1)
                result, requests = self.run_cli(module, directory, ['--include-published'], '1\ny\n')
                self.assertIn('wurde bereits veröffentlicht', result.output)
                self.assertIn('DRY RUN', result.output)
                self.assertEqual(len(requests), 2)

    def seed_previous_publication(self, module, directory):
        previous_event = deepcopy(EVENT)
        previous_event.update(uuid='old-event', title='Alter Titel')
        previous_event['date'].update(start_date='2098-12-31', start_time='17:00')
        with patch.object(module, 'DATABASE_PATH', Path(directory) / 'posts.sqlite3'):
            conn = module.init_database()
            try:
                if module is FACEBOOK:
                    module.remember_post(conn, previous_event, 'old-post')
                else:
                    module.remember_post(conn, previous_event, 'old-post', 'https://example.test/old-post')
                # Avoid sleeps and same-second timestamp comparisons.
                conn.execute("UPDATE published_events SET published_at = '2000-01-01 00:00:00'")
                conn.commit()
            finally:
                conn.close()
        return self.publication_records(directory)

    def publication_records(self, directory):
        with sqlite3.connect(Path(directory) / 'posts.sqlite3') as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute('SELECT * FROM published_events')]

    def test_confirmed_repeat_publish_updates_existing_record(self):
        for module in [FACEBOOK, MASTODON]:
            for status_url in ['https://example.test/new-post', None]:
                with self.subTest(platform=module.__name__, status_url=status_url), tempfile.TemporaryDirectory() as directory:
                    previous = self.seed_previous_publication(module, directory)
                    function = 'publish_text_post' if module is FACEBOOK else 'publish_mastodon_status'
                    value = 'new-post' if module is FACEBOOK else ('new-post', status_url)

                    def remote_success(*args, **kwargs):
                        self.assertEqual(self.publication_records(directory), previous)
                        return value

                    with patch.object(module, function, side_effect=remote_success) as publish:
                        result, _ = self.run_cli(
                            module, directory, ['--include-published', '--publish'], '1\ny\ny\n',
                        )
                        publish.assert_called_once()
                    self.assertIn('wurde bereits veröffentlicht', result.output)
                    self.assertIn('Gespeichert: date-1 -> new-post', result.output)
                    self.assertNotIn('UNIQUE', result.output)
                    self.assertNotIn('Fehler', result.output)
                    records = self.publication_records(directory)
                    self.assertEqual(len(records), 1)
                    record = records[0]
                    self.assertEqual(record['date_uuid'], 'date-1')
                    self.assertEqual(record['event_uuid'], EVENT['uuid'])
                    self.assertEqual(record['title'], EVENT['title'])
                    self.assertEqual(record['start_date'], EVENT['date']['start_date'])
                    self.assertEqual(record['start_time'], EVENT['date']['start_time'])
                    self.assertGreater(record['published_at'], previous[0]['published_at'])
                    id_column = 'facebook_post_id' if module is FACEBOOK else 'mastodon_status_id'
                    self.assertEqual(record[id_column], 'new-post')
                    if module is MASTODON:
                        self.assertEqual(record['mastodon_status_url'], status_url)

    def test_failed_repeat_publish_preserves_existing_record(self):
        for module in [FACEBOOK, MASTODON]:
            with self.subTest(platform=module.__name__), tempfile.TemporaryDirectory() as directory:
                previous = self.seed_previous_publication(module, directory)
                function = 'publish_text_post' if module is FACEBOOK else 'publish_mastodon_status'
                with patch.object(module, function, side_effect=RuntimeError('Remote failure')) as publish:
                    result, _ = self.run_cli(
                        module, directory, ['--include-published', '--publish'], '1\ny\ny\n',
                    )
                    publish.assert_called_once()
                self.assertIn('Remote failure', result.output)
                self.assertNotIn('Gespeichert:', result.output)
                self.assertEqual(self.publication_records(directory), previous)

    def test_repeat_publish_requires_both_confirmations_and_respects_dry_run(self):
        cases = [(['--publish'], '1\nn\n'), (['--publish'], '1\ny\nn\n'), ([], '1\ny\n')]
        for module in [FACEBOOK, MASTODON]:
            for args, user_input in cases:
                with self.subTest(platform=module.__name__, args=args, user_input=user_input), tempfile.TemporaryDirectory() as directory:
                    previous = self.seed_previous_publication(module, directory)
                    function = 'publish_text_post' if module is FACEBOOK else 'publish_mastodon_status'
                    with patch.object(module, function) as publish:
                        result, _ = self.run_cli(
                            module, directory, ['--include-published'] + args, user_input,
                        )
                        publish.assert_not_called()
                    self.assertIn('wurde bereits veröffentlicht', result.output)
                    if not args:
                        self.assertIn('DRY RUN', result.output)
                    self.assertEqual(self.publication_records(directory), previous)

    def test_filtering_sorting_and_limit(self):
        summaries = [
            dict(SUMMARY, start_date='2099-02-01', title='Später'),
            dict(SUMMARY, start_date='2000-01-01', title='Vergangen'),
            dict(SUMMARY, release_status='draft', title='Entwurf'),
            dict(SUMMARY, venue_city='Hamburg', title='Andere Stadt'),
            SUMMARY,
        ]
        for module in [FACEBOOK, MASTODON]:
            with self.subTest(platform=module.__name__), tempfile.TemporaryDirectory() as directory:
                result, _ = self.run_cli(module, directory, ['--city', 'flensburg', '--limit', '1'], '1\n', summaries)
                self.assertIn('1 Termine stehen zur Auswahl.', result.output)
                for title in ['Später', 'Vergangen', 'Entwurf', 'Andere Stadt']:
                    self.assertNotIn(title, result.output)

    def test_direct_selection_by_slug_and_date_uuid(self):
        for module in [FACEBOOK, MASTODON]:
            for identifier in ['209901011830', 'date-1']:
                with self.subTest(platform=module.__name__, identifier=identifier), tempfile.TemporaryDirectory() as directory:
                    args = ['--event-uuid', 'event-1', '--date-identifier', identifier]
                    summaries = [dict(SUMMARY, uuid='other-event'), SUMMARY]
                    result, requests = self.run_cli(module, directory, args, '', summaries)
                    self.assertIn('DRY RUN', result.output)
                    self.assertNotIn('Welche Events', result.output)
                    self.assertEqual(len(requests), 2)
                    with sqlite3.connect(Path(directory) / 'posts.sqlite3') as conn:
                        self.assertFalse(already_published(conn, 'date-1'))
                    result, _ = self.run_cli(module, directory, args + ['--publish'], 'n\n')
                    self.assertIn('Übersprungen.', result.output)
                    function = 'publish_text_post' if module is FACEBOOK else 'publish_mastodon_status'
                    value = 'post-direct' if module is FACEBOOK else ('post-direct', None)
                    with patch.object(module, function, return_value=value) as publish:
                        self.run_cli(module, directory, args + ['--publish'], 'y\n')
                        publish.assert_called_once()
                    with sqlite3.connect(Path(directory) / 'posts.sqlite3') as conn:
                        self.assertTrue(already_published(conn, 'date-1'))
                    result, requests = self.run_cli(module, directory, args, '', expected_exit=1)
                    self.assertIn('bereits', result.output)
                    self.assertEqual(len(requests), 1)

    def test_direct_publication_failure_does_not_record_success(self):
        for module in [FACEBOOK, MASTODON]:
            with self.subTest(platform=module.__name__), tempfile.TemporaryDirectory() as directory:
                function = 'publish_text_post' if module is FACEBOOK else 'publish_mastodon_status'
                with patch.object(module, function, side_effect=RuntimeError('Remote failure')):
                    result, _ = self.run_cli(
                        module, directory,
                        ['--publish', '--event-uuid', 'event-1', '--date-identifier', 'date-1'],
                        'y\n', expected_exit=1,
                    )
                self.assertIn('Remote failure', result.output)
                with sqlite3.connect(Path(directory) / 'posts.sqlite3') as conn:
                    self.assertFalse(already_published(conn, 'date-1'))

    def test_direct_selection_rejects_invalid_or_filtered_targets(self):
        args = ['--event-uuid', 'event-1', '--date-identifier', 'date-1']
        for module in [FACEBOOK, MASTODON]:
            for summaries in [[], [dict(SUMMARY, uuid='other')],
                              [dict(SUMMARY, date_uuid='other')], [SUMMARY, SUMMARY],
                              [dict(SUMMARY, release_status='draft')],
                              [dict(SUMMARY, start_date='2000-01-01')]]:
                with self.subTest(platform=module.__name__, summaries=summaries), tempfile.TemporaryDirectory() as directory:
                    _, requests = self.run_cli(module, directory, args, '', summaries, expected_exit=1)
                    self.assertEqual(len(requests), 1)
            for incomplete in [['--event-uuid', 'event-1'], ['--date-identifier', 'date-1']]:
                with self.subTest(platform=module.__name__, args=incomplete), tempfile.TemporaryDirectory() as directory:
                    result, requests = self.run_cli(module, directory, incomplete, '', expected_exit=2)
                    self.assertIn('gemeinsam', result.output)
                    self.assertEqual(requests, [])

    def test_confirmed_publish_records_platform_id(self):
        for module in [FACEBOOK, MASTODON]:
            with self.subTest(platform=module.__name__), tempfile.TemporaryDirectory() as directory:
                function = 'publish_text_post' if module is FACEBOOK else 'publish_mastodon_status'
                value = 'post-2' if module is FACEBOOK else ('post-2', 'https://example.test/post-2')
                with patch.object(module, function, return_value=value) as publish:
                    self.run_cli(module, directory, ['--publish'], '1\ny\n')
                    publish.assert_called_once()
                with sqlite3.connect(Path(directory) / 'posts.sqlite3') as conn:
                    self.assertTrue(already_published(conn, 'date-1'))


if __name__ == '__main__':
    unittest.main()
