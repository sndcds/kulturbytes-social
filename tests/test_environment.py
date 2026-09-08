import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote
import click
import httpx
from click.testing import CliRunner
from dotenv_support import IsolatedEnvironmentTestCase
from kulturbytes_common import credentials, environment
from kulturbytes_social.cli import cli
from test_publishers import FACEBOOK
from test_instagram import instagram
TOKEN = 'test-meta+/secret'
DERIVED = 'test-page-secret'

class EnvironmentTests(IsolatedEnvironmentTestCase):

    def test_path_ignores_cwd_and_installed_uses_xdg(self):
        # The base test isolates the real function; exercise its original definition here.
        from importlib.util import spec_from_file_location, module_from_spec
        import sys
        spec = spec_from_file_location('path_test_environment', environment.__file__)
        module = module_from_spec(spec)
        with patch.dict(sys.modules, {spec.name: module}):
            spec.loader.exec_module(module)
        root = Path(environment.__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as directory:
            before = Path.cwd()
            try:
                os.chdir(directory)
                self.assertEqual(module.get_env_file_path(), root / '.env')
                with patch.object(module, '__file__', str(Path(directory) / 'lib/python/site-packages/kulturbytes_common/environment.py')):
                    with patch.dict(os.environ, {'XDG_CONFIG_HOME': directory}):
                        self.assertEqual(module.get_env_file_path(), Path(directory) / 'kulturbytes-social/.env')
                    with patch.dict(os.environ, {'XDG_CONFIG_HOME': 'relative'}):
                        self.assertEqual(module.get_env_file_path(), Path.home() / '.config/kulturbytes-social/.env')
            finally:
                os.chdir(before)

    def test_literal_parsing_precedence_and_source(self):
        path = environment.get_env_file_path()
        path.write_text("# local\nMETA_SYSTEM_USER_ACCESS_TOKEN='${literal} # value'\nFACEBOOK_PAGE_ID=123\n", encoding='utf-8')
        with patch.dict(os.environ, {'META_SYSTEM_USER_ACCESS_TOKEN': 'ignored', 'FACEBOOK_PAGE_ID': '999'}), \
             patch.object(credentials, 'get_secret') as keyring:
            value = credentials.resolve_credential_source(credentials.META_SYSTEM_USER)
            self.assertEqual(value.value, '${literal} # value')
            self.assertEqual(value.source, 'dotenv')
            self.assertNotIn(value.value, repr(value))
            self.assertEqual(environment.get_config('FACEBOOK_PAGE_ID'), '123')
            self.assertEqual(os.environ['FACEBOOK_PAGE_ID'], '999')
            keyring.assert_not_called()

    def test_empty_dotenv_falls_back_and_empty_environment_suppresses_keyring(self):
        environment.get_env_file_path().write_text('META_SYSTEM_USER_ACCESS_TOKEN=\n')
        with patch.dict(os.environ, {'META_SYSTEM_USER_ACCESS_TOKEN': TOKEN}, clear=True), \
             patch.object(credentials, 'get_secret') as keyring:
            self.assertEqual(credentials.resolve_credential_source(credentials.META_SYSTEM_USER).source, 'environment')
            with patch.dict(os.environ, {'META_SYSTEM_USER_ACCESS_TOKEN': ''}):
                self.assertIsNone(credentials.resolve_credential(credentials.META_SYSTEM_USER))
            keyring.assert_not_called()

    def test_atomic_update_preserves_other_lines_and_deduplicates(self):
        path = environment.get_env_file_path()
        text = '# comment\r\nOTHER="value" # retained\r\n\r\nMETA_SYSTEM_USER_ACCESS_TOKEN=old # token comment\r\nMETA_SYSTEM_USER_ACCESS_TOKEN=duplicate\r\nLAST=1'
        path.write_bytes(text.encode())
        for token in [TOKEN, "quotes'\\and${literal}\nnewline"]:
            environment.set_dotenv_value('META_SYSTEM_USER_ACCESS_TOKEN', token)
            content = path.read_bytes().decode()
            self.assertIn('# comment\r\nOTHER="value" # retained\r\n\r\n', content)
            self.assertIn('LAST=1', content)
            self.assertIn('# token comment', content)
            self.assertEqual(content.count('META_SYSTEM_USER_ACCESS_TOKEN='), 1)
            self.assertEqual(environment.get_dotenv_value('META_SYSTEM_USER_ACCESS_TOKEN'), token)
            self.assertEqual(list(path.parent.iterdir()), [path])
            if os.name == 'posix':
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_new_file_permissions_and_append_without_newline(self):
        path = environment.get_env_file_path()
        environment.set_dotenv_value('META_SYSTEM_USER_ACCESS_TOKEN', TOKEN)
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        path.write_text('OTHER=value')
        environment.set_dotenv_value('META_SYSTEM_USER_ACCESS_TOKEN', TOKEN)
        self.assertIn('OTHER=value\n', path.read_text())

    def test_failed_writes_leave_original_and_no_temporary_file(self):
        path = environment.get_env_file_path()
        original = b'# original\nOTHER=value\n'
        for operation in ('replace', 'fsync'):
            path.write_bytes(original)
            with patch.object(environment.os, operation, side_effect=OSError(TOKEN)), \
                 self.assertRaises(environment.EnvironmentFileError) as error:
                environment.set_dotenv_value('META_SYSTEM_USER_ACCESS_TOKEN', TOKEN)
            self.assertNotIn(TOKEN, str(error.exception))
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_malformed_file_and_symlink_fail_without_exposing_contents(self):
        path = environment.get_env_file_path()
        path.write_text("META_SYSTEM_USER_ACCESS_TOKEN='" + TOKEN)
        with self.assertRaises(environment.EnvironmentFileError) as error:
            credentials.optional_credential(credentials.META_SYSTEM_USER)
        self.assertNotIn(TOKEN, str(error.exception))
        with self.assertRaises(environment.EnvironmentFileError):
            environment.set_dotenv_value('META_SYSTEM_USER_ACCESS_TOKEN', 'new')
        if os.name == 'posix':
            target = path.with_name('target')
            path.rename(target)
            path.symlink_to(target)
            with self.assertRaises(environment.EnvironmentFileError):
                environment.set_dotenv_value('META_SYSTEM_USER_ACCESS_TOKEN', 'new')
            self.assertTrue(path.is_symlink())

    def test_mastodon_uses_shared_dotenv_precedence(self):
        environment.get_env_file_path().write_text('MASTODON_ACCESS_TOKEN=dotenv-token\n')
        with patch.dict(os.environ, {'MASTODON_ACCESS_TOKEN': TOKEN}):
            self.assertEqual(credentials.resolve_credential(credentials.MASTODON), 'dotenv-token')
