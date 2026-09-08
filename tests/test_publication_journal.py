from copy import deepcopy
import importlib
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock

import click
import httpx
from click.testing import CliRunner
from dotenv_support import IsolatedEnvironmentTestCase
from kulturbytes_common.publications import (
    reserve_attempt, execute_publication, begin_remote_mutation, get_attempt, list_attempts,
    mark_failed, mark_remote_succeeded, mark_published, resolve_attempt, unresolved_attempt, RemoteRejected,
)
from kulturbytes_common.database import already_published
from kulturbytes_social.cli import cli
from test_publishers import EVENT, FACEBOOK, MASTODON, SUMMARY

INSTAGRAM = importlib.import_module('kulturbytes_instagram.cli')


class JournalTests(IsolatedEnvironmentTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / 'facebook.sqlite3'
        self.patch = patch.object(FACEBOOK, 'DATABASE_PATH', self.db)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.conn = FACEBOOK.init_database()
        self.addCleanup(self.conn.close)

    def finalize(self, post_id, post_url):
        FACEBOOK.remember_post(self.conn, EVENT, post_id)

    def publish(self):
        begin_remote_mutation()
        # Publishing intent is visible from another connection before the mutation.
        with sqlite3.connect(self.db) as observer:
            self.assertEqual(list_attempts(observer)[-1]['state'], 'publishing')
        return '123', None

    def test_success_repeat_and_legacy_records(self):
        execute_publication(self.conn, 'facebook', EVENT, self.publish, self.finalize)
        self.assertTrue(already_published(self.conn, 'date-1'))
        self.assertEqual(list_attempts(self.conn)[0]['state'], 'published')
        with self.assertRaises(click.ClickException):
            reserve_attempt(self.conn, 'facebook', EVENT)
        execute_publication(self.conn, 'facebook', EVENT, self.publish, self.finalize, allow_repeat=True)
        rows = list_attempts(self.conn)
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]['attempt_uuid'], rows[1]['attempt_uuid'])
        legacy = deepcopy(EVENT)
        legacy['date']['uuid'] = 'legacy-date'
        FACEBOOK.remember_post(self.conn, legacy, 'old-id')
        with self.assertRaises(click.ClickException):
            reserve_attempt(self.conn, 'facebook', legacy)
        self.assertTrue(already_published(self.conn, 'legacy-date'))

    def test_pre_remote_failure_releases_reservation(self):
        def fail():
            raise ValueError('bad local content')
        with self.assertRaises(ValueError):
            execute_publication(self.conn, 'facebook', EVENT, fail, self.finalize)
        self.assertEqual(list_attempts(self.conn)[0]['state'], 'failed')
        self.assertFalse(already_published(self.conn, 'date-1'))
        reserve_attempt(self.conn, 'facebook', EVENT)

    def test_definitive_rejection_vs_uncertain_transport(self):
        def rejected():
            begin_remote_mutation()
            raise RemoteRejected('HTTP 403')
        with self.assertRaises(RemoteRejected):
            execute_publication(self.conn, 'facebook', EVENT, rejected, self.finalize)
        self.assertEqual(list_attempts(self.conn)[0]['state'], 'failed')
        def timeout():
            begin_remote_mutation()
            raise httpx.ReadTimeout('https://secret:credential@private.invalid')
        with self.assertRaises(click.ClickException) as error:
            execute_publication(self.conn, 'facebook', EVENT, timeout, self.finalize)
        self.assertNotIn('credential', str(error.exception))
        self.assertEqual(list_attempts(self.conn)[-1]['state'], 'publishing')
        with self.assertRaises(click.ClickException):
            reserve_attempt(self.conn, 'facebook', EVENT, allow_repeat=True)

    def test_remote_success_survives_actual_sqlite_finalization_failure_and_recovery(self):
        self.conn.execute("CREATE TRIGGER reject_finalization BEFORE INSERT ON published_events BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        self.conn.commit()
        with self.assertRaises(click.ClickException) as error:
            execute_publication(self.conn, 'facebook', EVENT, self.publish, self.finalize)
        self.assertIn('Remote-ID=123', str(error.exception))
        attempt = list_attempts(self.conn)[0]
        self.assertEqual((attempt['state'], attempt['remote_id']), ('remote_succeeded', '123'))
        self.assertFalse(already_published(self.conn, 'date-1'))
        with sqlite3.connect(self.db) as restart:
            with self.assertRaises(click.ClickException):
                reserve_attempt(restart, 'facebook', EVENT, allow_repeat=True)
        with self.assertRaises(click.ClickException):
            resolve_attempt(self.conn, attempt['attempt_uuid'], 'failed', Mock())
        self.conn.execute('DROP TRIGGER reject_finalization')
        self.conn.commit()
        resolve_attempt(self.conn, attempt['attempt_uuid'], 'published', lambda event, post_id, url: FACEBOOK.remember_post(self.conn, event, post_id))
        self.assertTrue(already_published(self.conn, 'date-1'))
        self.assertEqual(get_attempt(self.conn, attempt['attempt_uuid'])['state'], 'published')

    def test_failure_to_journal_remote_id_retains_committed_blocker(self):
        with patch('kulturbytes_common.publications.mark_remote_succeeded', side_effect=sqlite3.OperationalError('full')):
            with self.assertRaises(click.ClickException) as error:
                execute_publication(self.conn, 'facebook', EVENT, self.publish, self.finalize)
        self.assertIn('123', str(error.exception))
        self.assertEqual(list_attempts(self.conn)[0]['state'], 'publishing')
        self.assertFalse(already_published(self.conn, 'date-1'))

    def test_crash_reservation_requires_explicit_resolution(self):
        attempt = reserve_attempt(self.conn, 'facebook', EVENT)
        with sqlite3.connect(self.db) as restart:
            with self.assertRaises(click.ClickException):
                reserve_attempt(restart, 'facebook', EVENT)
            resolve_attempt(restart, attempt, 'failed', Mock())
            next_attempt = reserve_attempt(restart, 'facebook', EVENT)
            self.assertNotEqual(attempt, next_attempt)

    def test_recovery_cli_confirms_and_never_makes_http_requests(self):
        attempt = reserve_attempt(self.conn, 'facebook', EVENT)
        mark_remote_succeeded(self.conn, attempt, '123')
        with patch.object(httpx.Client, 'send', side_effect=AssertionError('unexpected HTTP')):
            listed = CliRunner().invoke(cli, ['attempts', 'list', '--platform', 'facebook'])
            self.assertEqual(listed.exit_code, 0, listed.output)
            self.assertIn(attempt, listed.output)
            args = ['attempts', 'resolve', '--platform', 'facebook', attempt, '--outcome', 'published']
            declined = CliRunner().invoke(cli, args, input='n\n')
            self.assertEqual(declined.exit_code, 0, declined.output)
            self.assertFalse(already_published(self.conn, 'date-1'))
            recovered = CliRunner().invoke(cli, args, input='y\n')
            self.assertEqual(recovered.exit_code, 0, recovered.output)
            self.assertTrue(already_published(self.conn, 'date-1'))

    def test_unresolved_blocks_direct_even_with_include_published(self):
        attempt = reserve_attempt(self.conn, 'facebook', EVENT)
        mark_remote_succeeded(self.conn, attempt, '123')
        client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'data': {'events': [SUMMARY]}})))
        with patch('kulturbytes_common.workflow.httpx.Client', return_value=client):
            result = CliRunner().invoke(cli, ['facebook', '--event-uuid', EVENT['uuid'], '--date-identifier', 'date-1', '--include-published'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn(attempt, result.output)
        self.assertIn('Remote-ID=123', result.output)

    def test_all_platforms_journal_after_confirmation_and_before_remote(self):
        helpers = {FACEBOOK: 'publish_text_post', MASTODON: 'publish_mastodon_status', INSTAGRAM: 'publish_instagram_photo'}
        for module, helper in helpers.items():
            platform = module.__name__.split('.')[0].removeprefix('kulturbytes_')
            with self.subTest(platform=platform), patch.object(module, 'DATABASE_PATH', Path(self.directory.name) / f'{platform}-integration.sqlite3'):
                conn = module.init_database()
                self.addCleanup(conn.close)
                def remote(*args, **kwargs):
                    self.assertEqual(list_attempts(conn)[0]['state'], 'reserved')
                    begin_remote_mutation()
                    return ('123', 'https://example.test/123') if module is MASTODON else '123'
                with patch.object(module, helper, side_effect=remote) as call, patch('click.confirm', return_value=False), \
                     patch.object(INSTAGRAM, 'validate_image', return_value='https://api.kulturbytes.de/image.jpg'):
                    module.publish_event(Mock(), conn, EVENT, dry_run=True)
                    module.publish_event(Mock(), conn, EVENT, dry_run=False)
                    call.assert_not_called()
                    self.assertEqual(list_attempts(conn), [])
                    with patch('click.confirm', return_value=True):
                        module.publish_event(Mock(), conn, EVENT, dry_run=False, config=Mock())
                    call.assert_called_once()
                    self.assertEqual(list_attempts(conn)[0]['state'], 'published')

    def test_real_platform_post_paths_are_reserved_and_never_retried(self):
        configs = {
            FACEBOOK: FACEBOOK.FacebookConfig('123', 'test-secret', 'v26.0'),
            MASTODON: MASTODON.MastodonConfig('https://example.test', 'test-secret'),
            INSTAGRAM: INSTAGRAM.InstagramConfig('123', 'test-secret', 'https://example.test/v26.0'),
        }
        for module, config in configs.items():
            for result_kind in ('success', '403', '503', 'timeout', 'invalid_id'):
                platform = module.__name__.split('.')[0].removeprefix('kulturbytes_')
                db = Path(self.directory.name) / f'{platform}-{result_kind}.db'
                with self.subTest(platform=platform, result=result_kind), patch.object(module, 'DATABASE_PATH', db):
                    conn = module.init_database()
                    self.addCleanup(conn.close)
                    posts = []
                    def respond(request):
                        if request.method == 'POST':
                            self.assertEqual(list_attempts(conn)[0]['state'], 'publishing')
                            posts.append(request)
                            if result_kind == 'timeout':
                                raise httpx.ReadTimeout('test-secret in URL')
                            if result_kind in ('403', '503'):
                                return httpx.Response(int(result_kind), json={'error': {'message': 'test-secret rejected'}})
                            return httpx.Response(200, json={'id': 'test-secret' if result_kind == 'invalid_id' else '123', 'url': 'https://example.test/123'})
                        if '/image' in request.url.path:
                            return httpx.Response(200, content=b'\xff\xd8\xffjpeg')
                        return httpx.Response(200, json={'status_code': 'FINISHED'})
                    event = deepcopy(EVENT)
                    if module is INSTAGRAM:
                        event['images'] = {'main': {'url': 'https://api.kulturbytes.de/image.jpg'}}
                    with httpx.Client(transport=httpx.MockTransport(respond)) as client, patch('click.confirm', return_value=True):
                        if result_kind == 'success':
                            module.publish_event(client, conn, event, False, config=config)
                        else:
                            with self.assertRaises(click.ClickException) as error:
                                module.publish_event(client, conn, event, False, config=config)
                            self.assertNotIn('test-secret', str(error.exception))
                    self.assertEqual(len(posts), 2 if module is INSTAGRAM and result_kind == 'success' else 1)
                    state = list_attempts(conn)[0]['state']
                    self.assertEqual(state, {'success': 'published', '403': 'failed', '503': 'publishing', 'timeout': 'publishing', 'invalid_id': 'publishing'}[result_kind])

    def test_remote_url_cannot_leak_credentials(self):
        from kulturbytes_common.auth import remote_url
        for value in ('https://example.test/?token=test-secret', 'https://user:pass@example.test/post', {}, 'https://bad:port/post'):
            self.assertIsNone(remote_url(value, 'test-secret'))
        self.assertEqual(remote_url('https://example.test/@account/123', 'test-secret'), 'https://example.test/@account/123')
