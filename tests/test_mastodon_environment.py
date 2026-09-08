import os
import sqlite3
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

import click
import httpx
from click.testing import CliRunner

from dotenv_support import IsolatedEnvironmentTestCase
from kulturbytes_common import credentials, environment
from kulturbytes_social.cli import cli
from test_publishers import MASTODON as mastodon, EVENT, SUMMARY

TOKEN = 'mock-mastodon+/secret'
BASE = 'https://mastodon.example.test'


class MastodonEnvironmentTests(IsolatedEnvironmentTestCase):
    def test_all_credentials_share_source_and_empty_value_semantics(self):
        cases = [
            (TOKEN, 'env-token', 'keyring-token', TOKEN, 'dotenv'),
            (None, 'env-token', 'keyring-token', 'env-token', 'environment'),
            (None, None, 'keyring-token', 'keyring-token', 'keyring'),
            ('', 'env-token', 'keyring-token', 'env-token', 'environment'),
            ('   ', None, 'keyring-token', 'keyring-token', 'keyring'),
            (None, '', 'keyring-token', None, 'environment'),
            ('', '  ', 'keyring-token', None, 'environment'),
            (None, None, None, None, 'keyring'),
        ]
        for credential in (credentials.MASTODON, credentials.META_SYSTEM_USER,
                           credentials.FACEBOOK_PAGE, credentials.FACEBOOK_USER, credentials.INSTAGRAM):
            for dotenv, env, stored, expected, source in cases:
                with self.subTest(credential=credential.env_name, source=source):
                    environment.get_env_file_path().write_text(
                        f"{credential.env_name}='{dotenv}'\n" if dotenv is not None else '# no token\n')
                    with patch.dict(os.environ, {credential.env_name: env} if env is not None else {}, clear=True), \
                         patch.object(credentials, 'get_secret', return_value=stored) as keyring:
                        resolved = credentials.resolve_credential_source(credential)
                    self.assertEqual((resolved.value, resolved.source), (expected, source))
                    if source == 'keyring':
                        keyring.assert_called_once_with(credential.service, credential.username)
                    else:
                        keyring.assert_not_called()

    def test_base_url_precedence_and_normalization(self):
        for dotenv, env, expected in [(BASE+'/', 'https://ignored.test', BASE),
                                      (None, BASE, BASE), (None, None, 'https://norden.social')]:
            environment.get_env_file_path().write_text(f'MASTODON_BASE_URL={dotenv}\n' if dotenv else '')
            with patch.dict(os.environ, {'MASTODON_BASE_URL': env} if env else {}, clear=True):
                self.assertEqual(mastodon.load_base_url(), expected)

    def test_dotenv_base_url_retains_validation(self):
        for invalid in ('', 'ftp://host', 'https://user:pass@host', 'https://host/path',
                        'https://host?q=1', 'https://host#fragment', 'https://host:bad',
                        'https://host:99999', 'https://[bad', 'https://bad host'):
            environment.get_env_file_path().write_text(f"MASTODON_BASE_URL='{invalid}'\n")
            with patch.dict(os.environ, {'MASTODON_BASE_URL': BASE}), self.assertRaises(click.ClickException):
                mastodon.load_base_url()

    def test_auth_and_status_with_only_dotenv_are_read_only(self):
        path = environment.get_env_file_path()
        path.write_text(f'MASTODON_BASE_URL={BASE}\nMASTODON_ACCESS_TOKEN={TOKEN}\n')
        original = path.read_bytes()
        for failed in (False, True):
            calls = []
            def respond(request):
                calls.append(request)
                self.assertEqual(request.method, 'GET')
                self.assertEqual(str(request.url), BASE + '/api/v1/accounts/verify_credentials')
                self.assertEqual(request.headers['Authorization'], f'Bearer {TOKEN}')
                return httpx.Response(401, json={'error': TOKEN}) if failed else httpx.Response(
                    200, json={'id': '1', 'acct': 'kulturbytes'})
            client = httpx.Client(transport=httpx.MockTransport(respond))
            with patch.dict(os.environ, {}, clear=True), \
                 patch.object(credentials, 'get_secret', side_effect=AssertionError('Unexpected keyring lookup')), \
                 patch.object(mastodon, 'init_database') as db, \
                 patch.object(mastodon, 'run_publisher') as workflow, \
                 patch.object(mastodon, 'upload_mastodon_media') as media, \
                 patch.object(httpx, 'Client', return_value=client):
                result = CliRunner().invoke(cli, ['mastodon', '--check-auth'])
                self.assertEqual(result.exit_code, 1 if failed else 0, result.output)
                status = CliRunner().invoke(cli, ['mastodon', '--credentials', 'status'])
                self.assertEqual(status.exit_code, 0, status.output)
                self.assertIn('Access Token vorhanden', status.output)
                self.assertIn('Quelle: .env', status.output)
                db.assert_not_called()
                workflow.assert_not_called()
                media.assert_not_called()
            self.assertEqual(len(calls), 1)
            self.assertNotIn(TOKEN, result.output + status.output)
            self.assertEqual(path.read_bytes(), original)

    def test_missing_credentials_fail_without_prompt_or_database(self):
        for option in ('--check-auth', '--publish'):
            with patch.dict(os.environ, {}, clear=True), \
                 patch.object(credentials, 'get_secret', return_value=None), \
                 patch.object(click, 'prompt') as prompt, \
                 patch.object(mastodon, 'init_database') as db, patch.object(httpx, 'Client') as client:
                result = CliRunner().invoke(cli, ['mastodon', option])
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertIn('MASTODON_ACCESS_TOKEN fehlt', result.output)
                prompt.assert_not_called()
                db.assert_not_called()
                client.assert_not_called()

    def run_publisher(self, *, publish, image=False):
        path = environment.get_env_file_path()
        path.write_text(f'MASTODON_BASE_URL={BASE}\n' + (f'MASTODON_ACCESS_TOKEN={TOKEN}\n' if publish else ''))
        event, summary = deepcopy(EVENT), deepcopy(SUMMARY)
        event['date']['venue_city'] = summary['venue_city'] = 'Husum'
        if image:
            event['images'] = {'main': {'url': 'https://api.kulturbytes.de/picture.jpg', 'alt': 'Kulturabend im Saal'}}
        calls = []
        def respond(request):
            calls.append(request)
            if request.url.path == '/api/events':
                # Changes after initial config loading must not switch accounts mid-run.
                if publish:
                    path.write_text('MASTODON_ACCESS_TOKEN=changed\nMASTODON_BASE_URL=https://changed.test\n')
                return httpx.Response(200, json={'data': {'events': [summary]}})
            if request.url.path.startswith('/api/event/'):
                return httpx.Response(200, json={'data': event})
            if request.url.path == '/picture.jpg':
                self.assertNotIn('Authorization', request.headers)
                return httpx.Response(200, content=b'image', headers={'Content-Type': 'image/jpeg'})
            self.assertEqual(request.url.host, 'mastodon.example.test')
            if request.url.path == '/api/v2/instance':
                self.assertNotIn('Authorization', request.headers)
                return httpx.Response(200, json={'configuration': {'statuses': {'max_characters': 750}}})
            self.assertTrue(publish)
            self.assertEqual(request.headers['Authorization'], f'Bearer {TOKEN}')
            if request.url.path == '/api/v2/media':
                self.assertIn(b'Kulturabend im Saal', request.content)
                return httpx.Response(202, json={'id': 'media-1'})
            if request.url.path == '/api/v1/media/media-1':
                return httpx.Response(200, json={'url': BASE+'/image.jpg'})
            self.assertEqual(request.url.path, '/api/v1/statuses')
            data = parse_qs(request.content.decode())
            self.assertIn('#Husum', data['status'][0])
            if image:
                self.assertEqual(data['media_ids[]'], ['media-1'])
            return httpx.Response(200, json={'id': 'status-1', 'url': BASE+'/@kulturbytes/status-1'})
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
             patch.object(credentials, 'get_secret', side_effect=AssertionError('Unexpected keyring lookup')), \
             patch.object(mastodon, 'load_config', wraps=mastodon.load_config) as config, \
             patch.object(mastodon, 'DATABASE_PATH', Path(directory)/'posts.sqlite3'), \
             patch.object(httpx, 'Client', return_value=client):
            result = CliRunner().invoke(cli, ['mastodon', '--publish' if publish else '--dry-run', '--limit', '50', '--city', 'husum'],
                                        input='1\ny\n' if publish else '1\n')
            self.assertEqual(result.exit_code, 0, result.output + str(result.exception))
            self.assertEqual(config.call_count, 1 if publish else 0)
            with sqlite3.connect(Path(directory)/'posts.sqlite3') as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM published_events').fetchone(), (1 if publish else 0,))
        self.assertNotIn(TOKEN, result.output)
        return result, calls

    def test_publish_uses_one_dotenv_configuration_for_status_and_media(self):
        for image in (False, True):
            result, calls = self.run_publisher(publish=True, image=image)
            self.assertIn('Mastodon-Post erstellt', result.output)
            self.assertEqual(sum(r.url.path == '/api/v1/statuses' for r in calls), 1)
            self.assertEqual(sum(r.url.path == '/api/v2/media' for r in calls), int(image))
            self.assertEqual(sum(r.url.path == '/api/v1/media/media-1' for r in calls), int(image))

    def test_dry_run_uses_dotenv_instance_without_credentials(self):
        result, calls = self.run_publisher(publish=False)
        self.assertIn('DRY RUN', result.output)
        self.assertIn('/750', result.output)
        self.assertTrue(all(request.method == 'GET' for request in calls))
