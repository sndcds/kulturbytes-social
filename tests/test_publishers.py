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

from kulturbytes_common.database import already_published
from kulturbytes_common.events import build_address, build_hashtags, format_price
from kulturbytes_common.media import download_image
from kulturbytes_common.selection import parse_selection

with patch.dict(os.environ, {
    'FACEBOOK_PAGE_ID': 'test-page',
    'FACEBOOK_PAGE_ACCESS_TOKEN': 'test-facebook-token',
    'MASTODON_ACCESS_TOKEN': 'test-mastodon-token',
}):
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
    def run_cli(self, module, directory, args, user_input, summaries=None):
        requests = []

        def respond(request):
            requests.append(request)
            self.assertEqual(request.method, 'GET')
            if request.url.path == '/api/events':
                return httpx.Response(200, json={'data': {'events': summaries if summaries is not None else [SUMMARY]}})
            self.assertEqual(request.url.path, '/api/event/event-1/date/209901011830')
            return httpx.Response(200, json={'data': EVENT})
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(module, 'DATABASE_PATH', Path(directory) / 'posts.sqlite3'), patch(
            'kulturbytes_common.workflow.httpx.Client', return_value=client
        ):
            result = CliRunner().invoke(module.main, args, input=user_input)
        self.assertEqual(result.exit_code, 0, result.output + str(result.exception))
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
