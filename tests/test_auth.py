import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

import click
import httpx
from click.testing import CliRunner

from test_publishers import FACEBOOK, MASTODON, EVENT, SUMMARY
from test_instagram import instagram, EVENT as INSTAGRAM_EVENT

TOKEN = 'test-secret+/token'
ENV = {
    'FACEBOOK_PAGE_ID': '123', 'FACEBOOK_PAGE_ACCESS_TOKEN': TOKEN,
    'MASTODON_BASE_URL': 'https://norden.social', 'MASTODON_ACCESS_TOKEN': TOKEN,
    'INSTAGRAM_USER_ID': '123', 'INSTAGRAM_ACCESS_TOKEN': TOKEN,
}
PLATFORMS = [FACEBOOK, MASTODON, instagram]


class AuthTests(unittest.TestCase):
    def run_auth(self, module, response, *, env=None, args=None, expected_exit=0):
        requests = []

        def respond(request):
            requests.append(request)
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.headers['Authorization'], f'Bearer {TOKEN}')
            self.assertNotIn('access_token', request.url.params)
            self.assertIn('Kulturbytes-', request.headers['User-Agent'])
            if isinstance(response, Exception):
                raise response
            return response

        client_class = httpx.Client

        def make_client(**kwargs):
            return client_class(transport=httpx.MockTransport(respond), **kwargs)

        with patch.dict(os.environ, ENV if env is None else env, clear=True), patch(
            'kulturbytes_common.auth.httpx.Client', side_effect=make_client,
        ), patch.object(module, 'init_database') as database, patch.object(
            module, 'run_publisher',
        ) as workflow, patch.object(module, 'publish_event') as publish:
            result = CliRunner().invoke(module.main, args or ['--check-auth'])
        self.assertEqual(result.exit_code, expected_exit, result.output + str(result.exception))
        database.assert_not_called()
        workflow.assert_not_called()
        publish.assert_not_called()
        self.assertNotIn(TOKEN, result.output)
        self.assertNotIn(quote(TOKEN, safe=''), result.output)
        self.assertEqual(len(requests), 1)
        return result, requests[0]

    def test_auth_success_and_precedence(self):
        for module in PLATFORMS:
            for login in ['instagram', 'facebook']:
                with self.subTest(platform=module.__name__, login=login):
                    payload = {'id': '123', 'name': 'Kulturbytes', 'username': 'kulturbytes', 'acct': 'kulturbytes'}
                    result, request = self.run_auth(
                        module, httpx.Response(200, json=payload), env=dict(ENV, INSTAGRAM_LOGIN_TYPE=login),
                        args=['--check-auth', '--publish', '--city', 'Hamburg', '--limit', '0',
                              '--include-published', '--event-uuid', 'ignored'],
                    )
                    self.assertIn('Token gültig', result.output)
                    if module is MASTODON:
                        self.assertEqual(str(request.url), 'https://norden.social/api/v1/accounts/verify_credentials')
                        self.assertIn('@kulturbytes@norden.social', result.output)
                    else:
                        host = 'graph.instagram.com' if module is instagram and login == 'instagram' else 'graph.facebook.com'
                        self.assertEqual(request.url.host, host)
                        self.assertEqual(request.url.path, '/v26.0/123')
                        self.assertEqual(request.url.params['fields'], 'id,name' if module is FACEBOOK else 'id,username')
                        if module is instagram:
                            self.assertIn(f'Login-Typ: {login}', result.output)

    def test_auth_failures_and_redaction(self):
        for module in PLATFORMS:
            for status in [400, 401, 403, 500]:
                for payload in [{'error': {'code': 190, 'message': TOKEN}},
                                {'error': {'code': 190, 'error_subcode': 463, 'message': quote(TOKEN, safe='')}},
                                {'error': TOKEN}]:
                    with self.subTest(platform=module.__name__, status=status, payload=payload):
                        result, _ = self.run_auth(module, httpx.Response(status, json=payload), expected_exit=1)
                        self.assertIn('[REDACTED]', result.output)
                        self.assertIn(f'HTTP {status}', result.output)
                        if isinstance(payload['error'], dict) and payload['error'].get('error_subcode') == 463:
                            self.assertIn('abgelaufen', result.output)
        for module in PLATFORMS:
            with self.subTest(platform=module.__name__):
                self.run_auth(module, httpx.Response(200, json={'error': TOKEN}), expected_exit=1)
                self.run_auth(module, httpx.Response(502, text=TOKEN), expected_exit=1)
                self.run_auth(module, httpx.ConnectError(TOKEN), expected_exit=1)
                self.run_auth(module, httpx.Response(302, headers={'Location': 'https://example.test/' + TOKEN}), expected_exit=1)

    def test_invalid_account_responses(self):
        for module in PLATFORMS:
            for payload in [{}, [], None, {'id': '123'}]:
                with self.subTest(platform=module.__name__, payload=payload):
                    self.run_auth(module, httpx.Response(200, json=payload), expected_exit=1)
            if module is not MASTODON:
                result, _ = self.run_auth(module, httpx.Response(200, json={
                    'id': '999', 'name': 'Wrong page', 'username': 'wrong-account',
                }), expected_exit=1)
                self.assertIn('stimmt nicht', result.output)

    def test_success_output_redacts_echoed_token(self):
        for module in PLATFORMS:
            with self.subTest(platform=module.__name__):
                result, _ = self.run_auth(module, httpx.Response(200, json={
                    'id': '123', 'name': TOKEN, 'username': TOKEN, 'acct': TOKEN,
                }))
                self.assertIn('[REDACTED]', result.output)

    def test_import_and_help_without_credentials(self):
        for module in PLATFORMS:
            with self.subTest(platform=module.__name__), patch.dict(os.environ, {}, clear=True):
                # A fresh interpreter verifies imports rather than cached modules.
                result = subprocess.run([sys.executable, '-c', f'import {module.__name__}'],
                                        capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                result = CliRunner().invoke(module.main, ['--help'])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn('--check-auth', result.output)

    def test_missing_credentials_fail_before_network_or_database(self):
        for module in PLATFORMS:
            for option in ['--publish', '--check-auth']:
                with self.subTest(platform=module.__name__, option=option), patch.dict(os.environ, {}, clear=True), patch(
                    'httpx.Client',
                ) as client, patch.object(module, 'init_database') as database:
                    result = CliRunner().invoke(module.main, [option])
                    self.assertEqual(result.exit_code, 1, result.output)
                    self.assertIn('fehl', result.output)
                    client.assert_not_called()
                    database.assert_not_called()

    def test_strict_config_and_secret_repr(self):
        cases = [
            (FACEBOOK, 'FACEBOOK_PAGE_ID', ['', 'abc', '１２３', '123/456']),
            (FACEBOOK, 'FACEBOOK_PAGE_ACCESS_TOKEN', ['', '  ']),
            (FACEBOOK, 'FACEBOOK_GRAPH_API_VERSION', ['', '26', 'v26.0/path', 'v２６.０']),
            (MASTODON, 'MASTODON_ACCESS_TOKEN', ['', '  ']),
            (MASTODON, 'MASTODON_BASE_URL', ['', 'ftp://host', 'https://user:pass@host',
                                          'https://host/path', 'https://host?q=1', 'https://host#fragment',
                                          'https://host:bad', 'https://[bad', 'https://bad host']),
            (instagram, 'INSTAGRAM_USER_ID', ['', 'abc', '１２３']),
            (instagram, 'INSTAGRAM_ACCESS_TOKEN', ['', '  ']),
            (instagram, 'INSTAGRAM_LOGIN_TYPE', ['', 'invalid']),
            (instagram, 'INSTAGRAM_GRAPH_API_VERSION', ['', '26', 'v26.0/path', 'v２６.０']),
        ]
        for module, variable, values in cases:
            for value in values:
                with self.subTest(platform=module.__name__, variable=variable, value=value), patch.dict(
                    os.environ, dict(ENV, **{variable: value}), clear=True,
                ), self.assertRaises(click.ClickException):
                    module.load_config()
        for module in PLATFORMS:
            with patch.dict(os.environ, ENV, clear=True):
                self.assertNotIn(TOKEN, repr(module.load_config()))

    def test_publication_requests_use_lazy_credentials(self):
        cases = [
            (FACEBOOK, FACEBOOK.publish_text_post, '/v26.0/123/feed', 'post-123'),
            (FACEBOOK, FACEBOOK.publish_facebook_photo, '/v26.0/123/photos', 'post-123'),
            (MASTODON, MASTODON.upload_mastodon_media, '/api/v2/media', 'post-123'),
            (MASTODON, MASTODON.publish_mastodon_status, '/api/v1/statuses', ('post-123', None)),
        ]
        for module, publish, path, expected in cases:
            for status in [200, 401]:
                with self.subTest(function=publish.__name__, status=status), patch.dict(os.environ, ENV, clear=True):
                    requests = []

                    def respond(request):
                        requests.append(request)
                        self.assertEqual(request.method, 'POST')
                        self.assertEqual(request.url.path, path)
                        self.assertEqual(request.headers['Authorization'], f'Bearer {TOKEN}')
                        self.assertNotIn(TOKEN.encode(), request.content)
                        return httpx.Response(status, json={'id': 'post-123'} if status == 200 else {'error': TOKEN})

                    with httpx.Client(transport=httpx.MockTransport(respond)) as client, patch.object(
                        module, 'download_image', return_value=(b'image', 'image/jpeg', 'image.jpg'),
                    ):
                        if status == 200:
                            self.assertEqual(publish(client, EVENT), expected)
                        else:
                            with self.assertRaises(click.ClickException) as error:
                                publish(client, EVENT)
                            self.assertNotIn(TOKEN, str(error.exception))
                            self.assertIn('[REDACTED]', str(error.exception))
                    self.assertEqual(len(requests), 1)

    def test_mastodon_media_poll_uses_lazy_credentials(self):
        with patch.dict(os.environ, ENV, clear=True):
            requests = []

            def respond(request):
                requests.append(request)
                self.assertEqual(request.method, 'GET')
                self.assertEqual(request.url.path, '/api/v1/media/media-123')
                self.assertEqual(request.headers['Authorization'], f'Bearer {TOKEN}')
                return httpx.Response(200, json={'url': 'https://example.test/image.jpg'})

            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                MASTODON.wait_for_media(client, 'media-123')
            self.assertEqual(len(requests), 1)

    def test_dry_run_without_credentials(self):
        for module in PLATFORMS:
            with self.subTest(platform=module.__name__), tempfile.TemporaryDirectory() as directory:
                requests = []

                def respond(request):
                    requests.append(request)
                    self.assertEqual(request.method, 'GET')
                    self.assertNotIn('Authorization', request.headers)
                    self.assertEqual(request.url.host, 'api.kulturbytes.de')
                    if request.url.path == '/api/events':
                        return httpx.Response(200, json={'data': {'events': [SUMMARY]}})
                    if request.url.path == '/api/event/event-1/date/209901011830':
                        return httpx.Response(200, json={'data': INSTAGRAM_EVENT if module is instagram else EVENT})
                    self.assertEqual(request.url.path, '/api/image/image-1')
                    return httpx.Response(200, content=b'\xff\xd8\xffJPEG')

                database = Path(directory) / 'posts.sqlite3'
                client = httpx.Client(transport=httpx.MockTransport(respond))
                with patch.object(MASTODON, 'get_status_limit', return_value=500), patch.dict(os.environ, {}, clear=True), patch.object(module, 'DATABASE_PATH', database), patch(
                    'kulturbytes_common.workflow.httpx.Client', return_value=client,
                ):
                    result = CliRunner().invoke(module.main, ['--dry-run'], input='1\n')
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn('DRY RUN', result.output)
                self.assertEqual(len(requests), 3 if module is instagram else 2)
                with sqlite3.connect(database) as conn:
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM published_events').fetchone(), (0,))


if __name__ == '__main__':
    unittest.main()
