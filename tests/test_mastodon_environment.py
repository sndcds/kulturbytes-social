import os
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
