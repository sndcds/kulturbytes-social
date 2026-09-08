"""No live Meta calls or OS keyring access."""
import os
import unittest
from dotenv_support import IsolatedEnvironmentTestCase
from unittest.mock import patch
import httpx
from click.testing import CliRunner
from publisher_harness import cli
from kulturbytes_common.credentials import KeyringUnavailable
from kulturbytes_facebook import auth
from kulturbytes_facebook import publisher as facebook
OLD = 'old-page-secret'
USER = 'user-secret'
NEW = 'new-page-secret'
PAGE = {'id': '123', 'name': 'Kulturbytes'}
ACCOUNTS = {'data': [{**PAGE, 'access_token': NEW}]}
EXPIRED = {'error': {'code': 190, 'error_subcode': 463, 'message': OLD + USER}}

class RecoveryTests(IsolatedEnvironmentTestCase):

    def invoke(self, responses, *, env=None, stored=None, tty=False, input='', args=None):
        calls = []

        def handle(request):
            calls.append(request)
            self.assertEqual(request.method, 'GET')
            status, body = responses[len(calls)-1]
            return httpx.Response(status, json=body)
        client = httpx.Client(transport=httpx.MockTransport(handle))

        def get_secret(service, username):
            return (stored or {}).get(username)
        with patch.dict(os.environ, {'META_SYSTEM_USER_ACCESS_TOKEN': '', 'FACEBOOK_PAGE_ID': '123', **(env or {})}, clear=True), patch('kulturbytes_common.credentials.get_secret', side_effect=get_secret) as get, patch.object(auth, 'set_secret') as save, patch.object(auth, 'interactive', return_value=tty), patch.object(auth.httpx, 'Client', return_value=client):
            result = CliRunner().invoke(cli, ['facebook', *(args or ['--check-auth'])], input=input)
        for token in (OLD, USER, NEW):
            self.assertNotIn(token, result.output)
        return (result, calls, save, get)

    def test_valid_page_precedence(self):
        for env, stored in [({'FACEBOOK_PAGE_ACCESS_TOKEN': OLD}, {'page-access-token': NEW}),
                            ({}, {'page-access-token': OLD})]:
            result, calls, save, get = self.invoke([(200, PAGE)], env=env, stored=stored)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(calls[0].headers['Authorization'], f'Bearer {OLD}')
            self.assertNotIn('user-access-token', [c.args[1] for c in get.call_args_list])
            save.assert_not_called()

    def test_expired_env_and_keyring_recovery(self):
        for env, stored in [({'FACEBOOK_PAGE_ACCESS_TOKEN': OLD, 'FACEBOOK_USER_ACCESS_TOKEN': USER},
                             {'user-access-token': 'ignored'}),
                            ({}, {'page-access-token': OLD, 'user-access-token': USER})]:
            result, calls, save, _ = self.invoke([(400, EXPIRED), (200, ACCOUNTS), (200, PAGE)],
                                               env=env, stored=stored)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual([r.headers['Authorization'] for r in calls],
                             [f'Bearer {OLD}', f'Bearer {USER}', f'Bearer {NEW}'])
            save.assert_not_called()

    def test_pagination_and_exact_match(self):
        first = {'data': [{'id': '999', 'name': 'Kulturbytes', 'access_token': 'wrong'}],
                 'paging': {'next': 'https://graph.facebook.com/v26.0/me/accounts?access_token=unsafe',
                            'cursors': {'after': 'cursor-two'}}}
        result, calls, _, _ = self.invoke([(200, first), (200, ACCOUNTS), (200, PAGE)],
                                         env={'FACEBOOK_USER_ACCESS_TOKEN': USER})
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(calls[1].url.params['after'], 'cursor-two')
        self.assertNotIn('access_token', calls[1].url.params)

    def test_malformed_missing_and_unsafe_accounts(self):
        bodies = [{}, {'data': {}}, {'data': [None]}, {'data': [PAGE]}, {'data': []},
                  {**ACCOUNTS, 'paging': []},
                  {'data': [], 'paging': {'next': 'https://evil.example', 'cursors': {'after': 'x'}}},
                  {'data': [], 'paging': {'next': 'https://graph.facebook.com/v26.0/me/accounts'}},
                  {'data': [ACCOUNTS['data'][0]] * 2}]
        for body in bodies:
            with self.subTest(body=body):
                result, calls, save, _ = self.invoke([(200, body)], env={'FACEBOOK_USER_ACCESS_TOKEN': USER})
                self.assertNotEqual(result.exit_code, 0)
                save.assert_not_called()
                self.assertEqual(len(calls), 1)

    def test_invalid_validation_and_permissions_fail_closed(self):
        for body in [{'id': '999', 'name': 'other'}, {'id': '123'}, [],
                     {'error': {'code': 190}}, {'error': {'code': 10}}, {'error': {'code': 200}}]:
            result, _, save, _ = self.invoke([(200, ACCOUNTS), (200, body)],
                                            env={'FACEBOOK_USER_ACCESS_TOKEN': USER})
            self.assertNotEqual(result.exit_code, 0)
            save.assert_not_called()
        for code in (10, 200):
            result, calls, _, _ = self.invoke([(403, {'error': {'code': code}})],
                env={'FACEBOOK_PAGE_ACCESS_TOKEN': OLD, 'FACEBOOK_USER_ACCESS_TOKEN': USER})
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(len(calls), 1)

    def test_hidden_prompt_and_optional_save(self):
        for answer in ('y', 'n'):
            with patch.object(auth.click, 'prompt', wraps=auth.click.prompt) as prompt:
                result, _, save, _ = self.invoke([(400, EXPIRED), (200, ACCOUNTS), (200, PAGE)], tty=True,
                                                 stored={'page-access-token': OLD},
                                                 input=f'y\n{USER}\n{answer}\n')
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue(prompt.call_args.kwargs['hide_input'])
            if answer == 'y':
                save.assert_called_once_with('kulturbytes-social/facebook', 'page-access-token', NEW)
            else:
                save.assert_not_called()

    def test_decline_and_noninteractive_missing(self):
        for tty, input in [(True, 'n\n'), (False, '')]:
            with patch.object(auth.click, 'prompt') as prompt:
                result, calls, save, _ = self.invoke([], tty=tty, input=input)
            self.assertNotEqual(result.exit_code, 0)
            self.assertFalse(calls)
            prompt.assert_not_called()
            save.assert_not_called()

    def test_explicit_resolution_and_failed_publish_are_read_only(self):
        result, calls, _, _ = self.invoke([(200, ACCOUNTS), (200, PAGE)],
            env={'FACEBOOK_PAGE_ACCESS_TOKEN': OLD, 'FACEBOOK_USER_ACCESS_TOKEN': USER},
            args=['--resolve-page-token', '--publish'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(len(calls), 2)
        result, _, save, _ = self.invoke([(400, EXPIRED), (403, {'error': {'code': 200}})],
            stored={'page-access-token': OLD, 'user-access-token': USER}, args=['--publish'])
        self.assertNotEqual(result.exit_code, 0)
        save.assert_not_called()

    def test_cycle_and_empty_env_override(self):
        body = {'data': [], 'paging': {'next': 'https://graph.facebook.com/v26.0/me/accounts',
                                       'cursors': {'after': 'same'}}}
        result, calls, _, _ = self.invoke([(200, body)] * 2, env={'FACEBOOK_USER_ACCESS_TOKEN': USER})
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(len(calls), 2)
        result, calls, _, get = self.invoke([], env={'FACEBOOK_PAGE_ACCESS_TOKEN': '', 'FACEBOOK_USER_ACCESS_TOKEN': ''},
                                            stored={'page-access-token': OLD, 'user-access-token': USER})
        self.assertNotEqual(result.exit_code, 0)
        get.assert_not_called()

    def test_transport_and_keyring_failure_do_not_expose_secrets(self):
        with patch.dict(os.environ, {'META_SYSTEM_USER_ACCESS_TOKEN': '', 'FACEBOOK_PAGE_ID': '123', 'FACEBOOK_USER_ACCESS_TOKEN': USER}, clear=True), patch('kulturbytes_common.credentials.get_secret', side_effect=KeyringUnavailable('OS-Keyring ist nicht verfügbar.')), patch.object(auth, 'interactive', return_value=False):

            def fail(request):
                raise httpx.ConnectError(USER + OLD, request=request)
            client = httpx.Client(transport=httpx.MockTransport(fail))
            with patch.object(auth.httpx, 'Client', return_value=client):
                result = CliRunner().invoke(cli, ['facebook', '--publish'])
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn('Netzwerkfehler', result.output)
            self.assertNotIn(USER, result.output)
            self.assertNotIn(OLD, result.output)

    def test_management_cannot_swallow_resolve_action(self):
        result, calls, _, _ = self.invoke([], args=['--credentials', 'status', '--resolve-page-token'])
        self.assertEqual(result.exit_code, 2)
        self.assertFalse(calls)
