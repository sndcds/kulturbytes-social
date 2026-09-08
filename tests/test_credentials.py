import os
import unittest
from dotenv_support import IsolatedEnvironmentTestCase
from unittest.mock import patch
import click
import httpx
import keyring.errors
from click.testing import CliRunner
from kulturbytes_social.cli import cli
from kulturbytes_common import credentials as secrets
from test_publishers import FACEBOOK, MASTODON
from test_instagram import instagram
TOKEN = 'private-test-token'
OS_BACKEND = type('Keyring', (), {'__module__': 'keyring.backends.SecretService'})()
CASES = [(FACEBOOK, secrets.FACEBOOK_PAGE, 'page'), (FACEBOOK, secrets.FACEBOOK_USER, 'user'), (instagram, secrets.INSTAGRAM, 'access'), (MASTODON, secrets.MASTODON, 'access'), (FACEBOOK, secrets.META_SYSTEM_USER, 'meta'), (instagram, secrets.META_SYSTEM_USER, 'meta')]

class CredentialTests(IsolatedEnvironmentTestCase):

    def setUp(self):
        backend = patch.object(secrets.keyring, 'get_keyring', return_value=OS_BACKEND)
        self.backend = backend.start()
        self.addCleanup(backend.stop)
        for name in ['get_password', 'set_password', 'delete_password']:
            mocker = patch.object(secrets.keyring, name, return_value=None)
            setattr(self, name, mocker.start())
            self.addCleanup(mocker.stop)
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def invoke(self, module, args, user_input='', expected_exit=0):
        result = CliRunner().invoke(cli, [module.__name__.split('.')[0].removeprefix('kulturbytes_')] + args, input=user_input)
        self.assertEqual(result.exit_code, expected_exit, result.output + str(result.exception))
        self.assertNotIn(TOKEN, result.output)
        return result

    def test_env_override_including_empty_never_uses_keyring(self):
        self.backend.side_effect = RuntimeError(TOKEN)
        for _, credential, _ in CASES:
            for value, expected in [(TOKEN, TOKEN), ('', None), ('  ', None)]:
                with self.subTest(credential=credential, value=value), patch.dict(os.environ, {credential.env_name: value}):
                    self.assertEqual(secrets.resolve_credential(credential), expected)
        self.backend.assert_not_called()
        self.get_password.assert_not_called()

    def test_keyring_resolution_and_missing(self):
        for _, credential, _ in CASES:
            for value in [TOKEN, None]:
                with self.subTest(credential=credential, value=value):
                    self.get_password.return_value = value
                    self.assertEqual(secrets.resolve_credential(credential), value)
                    self.get_password.assert_called_with(credential.service, credential.username)

    def test_backend_failures_are_sanitized(self):
        for failing in [self.backend, self.get_password, self.set_password, self.delete_password]:
            with self.subTest(operation=failing):
                self.get_password.return_value = TOKEN
                failing.side_effect = RuntimeError(TOKEN)
                operation = (lambda: secrets.set_secret('service', 'user', TOKEN)) if failing is self.set_password else (
                    (lambda: secrets.delete_secret('service', 'user')) if failing is self.delete_password else
                    (lambda: secrets.get_secret('service', 'user')))
                with self.assertRaises(click.ClickException) as error:
                    operation()
                self.assertIn('OS-Keyring', str(error.exception))
                self.assertNotIn(TOKEN, str(error.exception))
                failing.side_effect = None

    def test_plaintext_and_disabled_backends_rejected(self):
        for module in ['keyrings.alt.file', 'keyring.backends.fail', 'keyring.backends.null']:
            self.backend.return_value = type('Keyring', (), {'__module__': module})()
            with self.subTest(module=module), self.assertRaises(click.ClickException):
                secrets.set_secret('service', 'user', TOKEN)
        self.set_password.assert_not_called()

    def test_status_presence_without_secret_details(self):
        for module, credential, selected in CASES:
            for present in [False, True]:
                with self.subTest(platform=module.__name__, selected=selected, present=present):
                    self.get_password.return_value = TOKEN if present else None
                    result = self.invoke(module, ['--credentials', 'status', '--credential', selected])
                    self.assertIn(credential.label + (' vorhanden' if present else ' nicht vorhanden'), result.output)
                    self.assertNotIn(str(len(TOKEN)), result.output)
        self.get_password.side_effect = RuntimeError(TOKEN)
        result = self.invoke(MASTODON, ['--credentials', 'status'], expected_exit=1)
        self.assertIn('OS-Keyring', result.output)

    def test_set_uses_hidden_prompt_and_stable_names(self):
        original_prompt = click.prompt
        for module, credential, selected in CASES:
            with self.subTest(platform=module.__name__, selected=selected), patch.object(
                click, 'prompt', wraps=original_prompt,
            ) as prompt:
                self.set_password.reset_mock()
                self.invoke(module, ['--credentials', 'set', '--credential', selected], TOKEN + '\n')
                self.set_password.assert_called_once_with(credential.service, credential.username, TOKEN)
                self.assertTrue(prompt.call_args.kwargs['hide_input'])
        self.set_password.reset_mock()
        self.invoke(FACEBOOK, ['--credentials', 'set'], TOKEN + '\n')
        self.set_password.assert_called_once_with(secrets.META_SYSTEM_USER.service, 'system-user-access-token', TOKEN)
        self.set_password.side_effect = RuntimeError(TOKEN)
        self.invoke(instagram, ['--credentials', 'set'], TOKEN + '\n', expected_exit=1)

    def test_delete_confirmation_missing_and_errors(self):
        for module, credential, selected in CASES:
            args = ['--credentials', 'delete', '--credential', selected]
            with self.subTest(platform=module.__name__, selected=selected):
                self.get_password.reset_mock()
                self.delete_password.reset_mock()
                self.invoke(module, args, 'n\n')
                self.get_password.assert_not_called()
                self.delete_password.assert_not_called()
                self.get_password.return_value = None
                result = self.invoke(module, args, 'y\n')
                self.assertIn('nicht vorhanden', result.output)
                self.delete_password.assert_not_called()
                self.get_password.return_value = TOKEN
                self.invoke(module, args, 'y\n')
                self.delete_password.assert_called_once_with(credential.service, credential.username)
        self.delete_password.side_effect = keyring.errors.PasswordDeleteError(TOKEN)
        self.get_password.side_effect = [TOKEN, None]
        self.assertFalse(secrets.delete_secret('service', 'user'))
        self.get_password.side_effect = None
        self.get_password.return_value = TOKEN
        result = self.invoke(MASTODON, ['--credentials', 'delete'], 'y\n', expected_exit=1)
        self.assertIn('OS-Keyring', result.output)

    def test_management_conflicts_and_no_token_argument(self):
        for module in [FACEBOOK, MASTODON, instagram]:
            for args in [['--credentials', 'set', '--publish'], ['--credentials', 'delete', '--check-auth'],
                         ['--credential', 'page' if module is FACEBOOK else 'access'], ['--token', TOKEN]]:
                self.invoke(module, args, expected_exit=2)
        self.backend.assert_not_called()

    def test_help_does_not_touch_keyring(self):
        self.backend.side_effect = RuntimeError(TOKEN)
        for module in [FACEBOOK, MASTODON, instagram]:
            result = self.invoke(module, ['--help'])
            self.assertIn('--credentials', result.output)
        self.backend.assert_not_called()
if __name__ == '__main__':
    unittest.main()
