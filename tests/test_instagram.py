import os
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx
from click.testing import CliRunner
from kulturbytes_social.cli import cli

from kulturbytes_common.database import already_published
from kulturbytes_common.events import get_event_url
from kulturbytes_common.formatting import strip_markdown
from kulturbytes_instagram import cli as instagram

EVENT = {
    'uuid': 'event-1', 'title': '**Kulturabend**', 'description': 'Detailbeschreibung.',
    'summary': 'Diese Detail-Summary darf nicht verwendet werden.',
    'tags': ['Musik', 'musik', 'Open Data', 'Kunst', 'Kultur', 'Lesung'],
    'images': {'main': {'url': 'https://api.kulturbytes.de/api/image/image-1'}},
    'date': {'uuid': 'date-1', 'slug': '209901011830', 'start_date': '2099-01-01',
             'start_time': '18:30', 'venue_name': 'Kulturhaus', 'venue_city': 'Flensburg'},
}
SUMMARY = {
    'uuid': 'event-1', 'date_uuid': 'date-1', 'date_slug': '209901011830',
    'release_status': 'released', 'start_date': '2099-01-01', 'start_time': '18:30',
    'title': 'Kulturabend', 'venue_city': 'Flensburg', 'summary': 'Zusammenfassung aus der Liste.',
}
ENV = {'INSTAGRAM_USER_ID': '123', 'INSTAGRAM_ACCESS_TOKEN': 'secret-token',
       'INSTAGRAM_LOGIN_TYPE': 'instagram', 'INSTAGRAM_GRAPH_API_VERSION': 'v26.0'}
DIRECT = ['--event-uuid', 'event-1', '--date-identifier', 'date-1']


class InstagramTests(unittest.TestCase):
    def setUp(self):
        lookup = patch('kulturbytes_common.credentials.get_secret', return_value=None)
        lookup.start()
        self.addCleanup(lookup.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / 'instagram.sqlite3'
        self.event = deepcopy(EVENT)
        self.summaries = [deepcopy(SUMMARY)]
        self.requests = []
        self.overrides = {}
        self.image = b'\xff\xd8\xffJPEG image fixture'

    def run_cli(self, args, user_input='', expected_exit=0, env=None):
        def respond(request):
            self.requests.append(request)
            path = request.url.path
            if path in self.overrides:
                return self.overrides[path](request)
            if path == '/api/events':
                self.assertEqual(request.method, 'GET')
                return httpx.Response(200, json={'data': {'events': self.summaries}})
            if path == '/api/event/event-1/date/209901011830':
                return httpx.Response(200, json={'data': self.event})
            if path == '/api/image/image-1':
                self.assertNotIn('Authorization', request.headers)
                return httpx.Response(200, content=self.image)
            self.assertEqual(request.headers['Authorization'], 'Bearer secret-token')
            self.assertNotIn('access_token', request.url.params)
            if path == '/v26.0/123':
                self.assertEqual(request.method, 'GET')
                return httpx.Response(200, json={'id': '123', 'username': 'kulturbytes'})
            if path == '/v26.0/123/media':
                self.assertEqual(request.method, 'POST')
                data = parse_qs(request.content.decode())
                self.assertEqual(data['image_url'], [EVENT['images']['main']['url']])
                self.assertIn(SUMMARY['summary'], data['caption'][0])
                self.assertNotIn(EVENT['summary'], data['caption'][0])
                return httpx.Response(200, json={'id': '456'})
            if path == '/v26.0/456':
                self.assertEqual(request.method, 'GET')
                self.assertEqual(request.url.params['fields'], 'status_code,status')
                return httpx.Response(200, json={'status_code': 'FINISHED'})
            if path == '/v26.0/123/media_publish':
                self.assertEqual(request.method, 'POST')
                self.assertEqual(parse_qs(request.content.decode()), {'creation_id': ['456']})
                return httpx.Response(200, json={'id': '789'})
            self.fail(f'Unexpected request: {request.method} {path}')

        client_class = httpx.Client
        def make_client(**kwargs):
            return client_class(transport=httpx.MockTransport(respond), **kwargs)
        with patch.dict(os.environ, ENV if env is None else env, clear=True), patch.object(
            instagram, 'DATABASE_PATH', self.database,
        ), patch('kulturbytes_common.workflow.httpx.Client', side_effect=make_client):
            result = CliRunner().invoke(cli, ['instagram'] + args, input=user_input)
        self.assertEqual(result.exit_code, expected_exit, result.output + str(result.exception))
        return result

    def assert_unpublished(self):
        with sqlite3.connect(self.database) as conn:
            self.assertFalse(already_published(conn, 'date-1'))
        self.assertFalse(any(r.url.path.endswith('/media_publish') for r in self.requests))

    def test_interactive_dry_run_without_credentials(self):
        result = self.run_cli([], '1\n', env={})
        self.assertIn('DRY RUN', result.output)
        self.assertIn(SUMMARY['summary'], result.output)
        self.assertNotIn('**', result.output)
        self.assertTrue(all(r.method == 'GET' for r in self.requests))
        self.assert_unpublished()

    def test_direct_dry_run_by_both_identifiers(self):
        for identifier in ['date-1', '209901011830']:
            with self.subTest(identifier=identifier):
                result = self.run_cli(['--event-uuid', 'event-1', '--date-identifier', identifier], env={})
                self.assertIn('DRY RUN', result.output)
                self.assertNotIn('Welche Events', result.output)
        self.assert_unpublished()

    def test_empty_summary_uses_detail_description(self):
        self.summaries[0]['summary'] = '  '
        result = self.run_cli(DIRECT, env={})
        self.assertIn(EVENT['description'], result.output)
        self.assertNotIn(EVENT['summary'], result.output)

    def test_publication_confirmation_and_success(self):
        result = self.run_cli(DIRECT + ['--publish'], 'n\n')
        self.assertIn('Übersprungen', result.output)
        self.assert_unpublished()
        self.requests.clear()
        self.run_cli(DIRECT + ['--publish'], 'y\n')
        self.assertEqual([r.url.path for r in self.requests[-3:]],
                         ['/v26.0/123/media', '/v26.0/456', '/v26.0/123/media_publish'])
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(conn.execute('SELECT instagram_media_id FROM published_events').fetchone(), ('789',))
        self.requests.clear()
        self.run_cli(DIRECT, expected_exit=1)
        self.assertEqual(len(self.requests), 1)
        # Re-publication requires both duplicate and publication confirmation.
        self.run_cli(DIRECT + ['--publish', '--include-published'], 'y\ny\n')
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM published_events').fetchone(), (1,))

    def test_facebook_login_uses_facebook_host(self):
        self.run_cli(DIRECT + ['--publish'], 'y\n', env=dict(ENV, INSTAGRAM_LOGIN_TYPE='facebook'))
        self.assertTrue(all(r.url.host == 'graph.facebook.com' for r in self.requests if '/v26.0/' in r.url.path))

    def test_missing_credentials_and_help(self):
        self.run_cli(DIRECT + ['--publish'], expected_exit=1, env={})
        self.assertFalse(self.requests)
        self.assertIn('--date-identifier', self.run_cli(['--help'], env={}).output)

    def test_incomplete_direct_arguments(self):
        self.run_cli(['--event-uuid', 'event-1'], expected_exit=2)
        self.assertFalse(self.requests)

    def test_filters_and_missing_event(self):
        for changes in [{'release_status': 'draft'}, {'start_date': '2000-01-01'}, {'uuid': 'other'}]:
            with self.subTest(changes=changes):
                self.summaries = [dict(SUMMARY, **changes)]
                self.run_cli(DIRECT, expected_exit=1)
        self.summaries = [SUMMARY]
        self.run_cli(DIRECT + ['--city', 'Hamburg'], expected_exit=1)
        self.assertTrue(all(r.url.path == '/api/events' for r in self.requests))

    def test_missing_image_blocks_publication(self):
        self.event.pop('images')
        result = self.run_cli(DIRECT + ['--publish'], 'y\n', expected_exit=1)
        self.assertIn('benötigt ein Hauptbild', result.output)
        self.assert_unpublished()

    def test_non_jpeg_blocks_publication(self):
        self.image = b'RIFF webp'
        result = self.run_cli(DIRECT + ['--publish'], 'y\n', expected_exit=1)
        self.assertIn('kein JPEG', result.output)
        self.assert_unpublished()

    def test_api_failures_do_not_record_success_and_redact_token(self):
        for path in ['/v26.0/123/media', '/v26.0/456', '/v26.0/123/media_publish']:
            with self.subTest(path=path):
                self.requests.clear()
                self.overrides = {path: lambda r: httpx.Response(400, json={'error': {'message': 'secret-token denied'}})}
                result = self.run_cli(DIRECT + ['--publish'], 'y\n', expected_exit=1)
                self.assertNotIn('secret-token', result.output)
                self.assertIn('[REDACTED]', result.output)
                with sqlite3.connect(self.database) as conn:
                    self.assertFalse(already_published(conn, 'date-1'))

    def test_invalid_creation_response_does_not_publish(self):
        for payload in [{}, {'id': None}, [], {'error': 'secret-token'}]:
            with self.subTest(payload=payload):
                self.overrides = {'/v26.0/123/media': lambda r: httpx.Response(200, json=payload)}
                result = self.run_cli(DIRECT + ['--publish'], 'y\n', expected_exit=1)
                self.assertNotIn('secret-token', result.output)
                self.assert_unpublished()

    def test_container_error_and_timeout_do_not_publish(self):
        for status in ['ERROR', 'EXPIRED', 'PUBLISHED', 'IN_PROGRESS', None]:
            with self.subTest(status=status):
                self.overrides = {'/v26.0/456': lambda r: httpx.Response(200, json={'status_code': status})}
                with patch.object(instagram.time, 'sleep'):
                    self.run_cli(DIRECT + ['--publish'], 'y\n', expected_exit=1)
                self.assert_unpublished()

    def test_waits_for_processing_before_publishing(self):
        statuses = iter(['IN_PROGRESS', 'FINISHED'])
        self.overrides = {'/v26.0/456': lambda r: httpx.Response(200, json={'status_code': next(statuses)})}
        with patch.object(instagram.time, 'sleep') as sleep:
            self.run_cli(DIRECT + ['--publish'], 'y\n')
            sleep.assert_called_once_with(60)

    def test_caption_limit_preserves_url_and_required_hashtags(self):
        event = deepcopy(EVENT)
        event['summary'] = '**Langer Text** ' * 1000
        caption = instagram.build_instagram_caption(event)
        self.assertLessEqual(len(caption), 2200)
        self.assertIn(get_event_url(event), caption)
        self.assertNotIn('**', caption)
        hashtags = caption.splitlines()[-1].split()
        self.assertEqual(len(hashtags), 5)
        self.assertIn('#Kulturbytes', hashtags)
        self.assertIn('#Flensburg', hashtags)
        event['title'] = 'A' * 2300
        with self.assertRaises(ValueError):
            instagram.build_instagram_caption(event)

    def test_shared_markdown_normalization(self):
        self.assertEqual(strip_markdown(r'**Text** 7\. September [Website](https://example.org)'),
                         'Text 7. September Website: https://example.org')


if __name__ == '__main__':
    unittest.main()
