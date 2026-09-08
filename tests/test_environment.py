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

    def test_mastodon_keeps_environment_and_keyring_semantics(self):
        environment.get_env_file_path().write_text('MASTODON_ACCESS_TOKEN=ignored\n')
        with patch.dict(os.environ, {'MASTODON_ACCESS_TOKEN': TOKEN}):
            self.assertEqual(credentials.resolve_credential(credentials.MASTODON), TOKEN)


class BootstrapTests(IsolatedEnvironmentTestCase):
    def invoke(self, platform, *, source='environment', fail=False, tty=False, publish=False, write_failure=False):
        module = FACEBOOK if platform == 'facebook' else instagram
        path = environment.get_env_file_path()
        original = b'# keep this\nFACEBOOK_PAGE_ID=123\nINSTAGRAM_USER_ID=123\n\nOTHER=value\n'
        if source == 'dotenv':
            original += f'META_SYSTEM_USER_ACCESS_TOKEN={TOKEN}\n'.encode()
        path.write_bytes(original)
        if os.name == 'posix':
            path.chmod(0o644)
        calls = []
        client_class = httpx.Client
        def handle(request):
            calls.append(request)
            self.assertEqual(path.read_bytes(), original)  # Still not persisted during validation.
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.host, 'graph.facebook.com')
            if request.url.path == '/v26.0/me/accounts':
                self.assertEqual(request.headers['Authorization'], f'Bearer {TOKEN}')
                return httpx.Response(200, json={'data': [{'id': '999', 'name': 'Other'},
                    {'id': '123', 'name': 'Page', 'access_token': DERIVED}]})
            self.assertEqual(request.url.path, '/v26.0/123')
            self.assertEqual(request.headers['Authorization'], f'Bearer {DERIVED if platform == "facebook" else TOKEN}')
            if fail:
                return httpx.Response(400, json={'error': {'code': 190, 'message': quote(TOKEN, safe='')}})
            return httpx.Response(200, json={'id': '123', 'name': 'Page', 'username': 'profile'})
        env = {'FACEBOOK_PAGE_ID': '999', 'INSTAGRAM_USER_ID': '999'}
        if source in ('dotenv', 'environment'):
            env['META_SYSTEM_USER_ACCESS_TOKEN'] = TOKEN if source == 'environment' else 'ignored-env'
        original_set = environment.set_dotenv_value
        with patch.dict(os.environ, env, clear=True), \
             patch.object(credentials, 'get_secret', side_effect=lambda service, name: TOKEN if source == 'keyring' and service.endswith('/meta') else None), \
             patch.object(credentials, 'set_secret') as save_keyring, \
             patch.object(credentials, 'delete_secret') as delete_keyring, \
             patch.object(credentials, 'interactive', return_value=tty), \
             patch.object(click, 'prompt', wraps=click.prompt) as prompt, \
             patch.object(httpx, 'Client', side_effect=lambda **kw: client_class(transport=httpx.MockTransport(handle), **kw)), \
             patch.object(module, 'init_database') as db, patch.object(module, 'run_publisher') as workflow, \
             patch.object(credentials, 'set_dotenv_value', side_effect=environment.EnvironmentFileError('Schreibfehler') if write_failure else original_set):
            result = CliRunner().invoke(cli, [platform, '--publish' if publish else '--check-auth'], input=TOKEN+'\n')
            save_keyring.assert_not_called()
            delete_keyring.assert_not_called()
            if result.exit_code or not publish:
                db.assert_not_called()
                workflow.assert_not_called()
            if source == 'prompt' and tty:
                self.assertTrue(prompt.call_args.kwargs['hide_input'])
            else:
                prompt.assert_not_called()
        for secret in (TOKEN, DERIVED, quote(TOKEN, safe='')):
            self.assertNotIn(secret, result.output)
        return result, original, calls

    def test_valid_fallbacks_persist_after_validation(self):
        for platform in ('facebook', 'instagram'):
            for source in ('environment', 'keyring', 'prompt', 'dotenv'):
                with self.subTest(platform=platform, source=source):
                    result, original, _ = self.invoke(platform, source=source, tty=source == 'prompt')
                    self.assertEqual(result.exit_code, 0, result.output + str(result.exception))
                    path = environment.get_env_file_path()
                    self.assertEqual(environment.get_dotenv_value('META_SYSTEM_USER_ACCESS_TOKEN'), TOKEN)
                    self.assertNotIn(DERIVED, path.read_text())
                    self.assertTrue(path.read_bytes().startswith(original))
                    if os.name == 'posix':
                        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_failed_validation_never_changes_file_or_keyring_or_database(self):
        for platform in ('facebook', 'instagram'):
            for source in ('environment', 'keyring', 'prompt', 'dotenv'):
                result, original, _ = self.invoke(platform, source=source, fail=True, tty=source == 'prompt', publish=True)
                self.assertNotEqual(result.exit_code, 0)
                self.assertEqual(environment.get_env_file_path().read_bytes(), original)

    def test_noninteractive_missing_never_prompts(self):
        for platform in ('facebook', 'instagram'):
            result, original, calls = self.invoke(platform, source='missing', publish=True)
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn('META_SYSTEM_USER_ACCESS_TOKEN fehlt', result.output)
            self.assertFalse(calls)
            self.assertEqual(environment.get_env_file_path().read_bytes(), original)

    def test_failed_persistence_stops_publication(self):
        for platform in ('facebook', 'instagram'):
            result, original, _ = self.invoke(platform, publish=True, write_failure=True)
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(environment.get_env_file_path().read_bytes(), original)

    def test_status_reports_source_without_validating_or_writing(self):
        for platform in ('facebook', 'instagram'):
            for source, label in [('dotenv', '.env'), ('environment', 'Environment'), ('keyring', 'OS-Keyring')]:
                path = environment.get_env_file_path()
                path.write_text(f'META_SYSTEM_USER_ACCESS_TOKEN={TOKEN}\n' if source == 'dotenv' else '# unchanged\n')
                before = path.read_bytes()
                with patch.dict(os.environ, {'META_SYSTEM_USER_ACCESS_TOKEN': TOKEN} if source == 'environment' else {}, clear=True), \
                     patch.object(credentials, 'get_secret', return_value=TOKEN), \
                     patch.object(httpx, 'Client') as client:
                    result = CliRunner().invoke(cli, [platform, '--credentials', 'status'])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn(f'Quelle: {label}', result.output)
                self.assertNotIn(TOKEN, result.output)
                self.assertEqual(path.read_bytes(), before)
                client.assert_not_called()

    def test_publication_keeps_validated_credential_after_file_changes(self):
        from test_meta_credentials import MetaTests
        # Simulate another process replacing the primary value immediately after persistence.
        def concurrent_change(name, value):
            environment.set_dotenv_value(name, 'concurrent-replacement')
        for platform in ('facebook', 'instagram'):
            with patch.object(credentials, 'set_dotenv_value', side_effect=concurrent_change):
                result, calls, _ = MetaTests().invoke(platform, publish=True)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertTrue(any(request.method == 'POST' for request in calls))

    def test_dry_run_never_reads_or_writes_auth_file(self):
        from test_publishers import PublisherTests
        from test_instagram import InstagramTests
        with patch.object(environment, 'read_env_file', side_effect=AssertionError('Unexpected auth read')):
            with tempfile.TemporaryDirectory() as directory:
                result, _ = PublisherTests().run_cli(FACEBOOK, directory, ['--dry-run'], '1\n')
                self.assertIn('DRY RUN', result.output)
            case = InstagramTests()
            case.setUp()
            try:
                result = case.run_cli(['--dry-run'], '1\n', env={})
                self.assertIn('DRY RUN', result.output)
            finally:
                case.doCleanups()
