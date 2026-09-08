"""CLI contract tests: backend HTTP only, local confirmation and no POST retry."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
from uuid import uuid4
import httpx
from click.testing import CliRunner
from dotenv_support import IsolatedEnvironmentTestCase, HTTPXClient
from kulturbytes_social.cli import cli
from test_publishers import SUMMARY

TOKEN = 'local-api-test-token'
ATTEMPT = str(uuid4())
PREVIEW = {'text': '📅 Kulturabend\nListen-Zusammenfassung\n👉 https://kulturbytes.de/de/veranstaltung/event-1/209901011830\n#Kulturbytes #Flensburg',
           'image_url': 'https://api.kulturbytes.de/api/image/image-1', 'content_sha256': 'a'*64}


class CLIClientTests(IsolatedEnvironmentTestCase):
    def invoke(self, platform='facebook', args=(), user_input='', published=False, failure=None):
        calls = []
        summary = {**SUMMARY, 'published': published}
        def handle(request):
            calls.append(request)
            self.assertEqual(request.url.host, 'backend.test')
            self.assertEqual(request.headers['Authorization'], f'Bearer {TOKEN}')
            self.assertNotIn(TOKEN, str(request.url))
            path = request.url.path
            if failure:
                return failure(request)
            if path.endswith('/preview'):
                return httpx.Response(200, json=PREVIEW)
            if path.endswith('/publications'):
                return httpx.Response(201, json={'remote_id': '456', 'attempt_id': ATTEMPT})
            if path.endswith('/check-auth') or path.endswith('/resolve'):
                return httpx.Response(200, json={'status': 'ok'})
            if path.endswith('/events'):
                return httpx.Response(200, json=[summary])
            if '/events/' in path:
                return httpx.Response(200, json={'summary': summary})
            if path.endswith('/publication-attempts'):
                return httpx.Response(200, json=[{'id': ATTEMPT, 'platform': 'facebook', 'state': 'publishing'}])
            if '/publication-attempts/' in path:
                return httpx.Response(200, json={'id': ATTEMPT, 'platform': 'facebook', 'state': 'publishing'})
            raise AssertionError(path)
        with patch.dict(os.environ, {'KULTURBYTES_SOCIAL_API_URL': 'http://backend.test', 'KULTURBYTES_SOCIAL_API_TOKEN': TOKEN}, clear=True), \
             patch('kulturbytes_social.client.httpx.Client', side_effect=lambda **kw: HTTPXClient(transport=httpx.MockTransport(handle), **kw)), \
             patch('kulturbytes_common.credentials.get_secret', side_effect=AssertionError('CLI must not resolve platform secrets')):
            result = CliRunner().invoke(cli, [platform, *args], input=user_input)
        self.assertNotIn(TOKEN, result.output)
        return result, calls

    def test_interactive_preview_for_all_platforms(self):
        for platform in ('facebook', 'instagram', 'mastodon'):
            result, calls = self.invoke(platform, user_input='1\n')
            self.assertEqual(result.exit_code, 0, str(result.exception))
            self.assertIn('DRY RUN', result.output)
            self.assertIn(PREVIEW['text'], result.output)
            self.assertEqual([r.url.path for r in calls], ['/api/v1/events', '/api/v1/publications/preview'])

    def test_selection_exit_and_publish_confirmation(self):
        for user_input, count in [('\n', 1), ('1\nn\n', 2), ('1\ny\n', 3)]:
            result, calls = self.invoke(args=['--publish'], user_input=user_input)
            self.assertEqual(result.exit_code, 0, str(result.exception)); self.assertEqual(len(calls), count)
        self.assertEqual(json.loads(calls[-1].content)['expected_content_sha256'], PREVIEW['content_sha256'])

    def test_repeat_needs_extra_confirmation_including_dry_run(self):
        cases = [([], '1\nn\n', 1), ([], '1\ny\n', 2), (['--publish'], '1\ny\nn\n', 2), (['--publish'], '1\ny\ny\n', 3)]
        for args, user_input, count in cases:
            result, calls = self.invoke(args=['--include-published', *args], user_input=user_input, published=True)
            self.assertEqual(result.exit_code, 0, str(result.exception))
            self.assertEqual(len(calls), count)
        self.assertIs(json.loads(calls[-1].content)['force_repeat'], True)

    def test_direct_identifiers_skip_numbered_selection_and_keep_confirmation(self):
        for identifier in ('date-1', SUMMARY['date_slug']):
            result, calls = self.invoke(args=['--event-uuid', 'event-1', '--date-identifier', identifier, '--limit', '1'])
            self.assertEqual(result.exit_code, 0, str(result.exception))
            self.assertNotIn('Welche Events', result.output)
            self.assertTrue(calls[0].url.path.endswith('/' + identifier))
            self.assertNotIn('limit', calls[0].url.params)
        result, calls = self.invoke(args=['--event-uuid', 'event-1'])
        self.assertEqual(result.exit_code, 2); self.assertEqual(calls, [])

    def test_filters_and_auth_use_backend(self):
        result, calls = self.invoke(args=['--city', 'Flensburg', '--limit', '0'], user_input='\n')
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(calls[0].url.params['city'], 'Flensburg')
        self.assertEqual(calls[0].url.params['limit'], '0')
        for platform in ('facebook', 'instagram', 'mastodon'):
            result, calls = self.invoke(platform, args=['--check-auth', '--event-uuid', 'ignored'])
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0].url.path.endswith(f'/{platform}/check-auth'))

    def test_backend_errors_are_nonzero_sanitized_and_mutations_not_retried(self):
        def failure(request):
            return httpx.Response(503, json={'detail': {'code': 'database_unavailable', 'message': 'Unavailable ' + TOKEN}})
        result, calls = self.invoke(args=['--check-auth'], failure=failure)
        self.assertEqual(result.exit_code, 1); self.assertEqual(len(calls), 1)
        def transport_failure(request): raise httpx.ReadTimeout(TOKEN)
        result, calls = self.invoke(args=['--check-auth'], failure=transport_failure)
        self.assertEqual(result.exit_code, 1); self.assertEqual(len(calls), 1)
        result, calls = self.invoke(args=['--event-uuid', 'event-1', '--date-identifier', 'date-1'], failure=lambda r: httpx.Response(409, json={'detail': {'code': 'publication_conflict', 'message': 'blocked'}}))
        self.assertEqual(result.exit_code, 1); self.assertEqual(len(calls), 1)

    def test_attempt_list_and_resolution_use_http_and_confirm(self):
        result, calls = self.invoke('attempts', args=['list', '--platform', 'facebook', '--active', '--limit', '0'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn(ATTEMPT, result.output)
        for answer, count in [('n\n', 1), ('y\n', 2)]:
            result, calls = self.invoke('attempts', args=['resolve', ATTEMPT, '--platform', 'facebook', '--outcome', 'failed'], user_input=answer)
            self.assertEqual(result.exit_code, 0, str(result.exception)); self.assertEqual(len(calls), count)
        self.assertIs(json.loads(calls[-1].content)['confirmed'], True)

    def test_help_and_import_require_no_backend_or_platform_credentials(self):
        with patch.dict(os.environ, {}, clear=True), patch('httpx.Client', side_effect=AssertionError('help uses network')):
            for args in ([], ['facebook'], ['instagram'], ['mastodon'], ['attempts'], ['attempts', 'list'], ['attempts', 'resolve']):
                result = CliRunner().invoke(cli, [*args, '--help'])
                self.assertEqual(result.exit_code, 0, str(result.exception))
        script = 'import sys; from kulturbytes_social.cli import cli; assert "sqlalchemy" not in sys.modules; assert "kulturbytes_facebook.publisher" not in sys.modules'
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
