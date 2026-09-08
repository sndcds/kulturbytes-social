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
        FACEBOOK.remember_post(self.conn, EVENT, post_id, commit=False)

    def publish(self):
        begin_remote_mutation("facebook_feed")
        # Publishing intent is visible from another connection before the mutation.
        with sqlite3.connect(self.db) as observer:
            self.assertEqual(list_attempts(observer)[0]['state'], 'publishing')
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
            begin_remote_mutation("facebook_feed")
            raise RemoteRejected('HTTP 403')
        with self.assertRaises(RemoteRejected):
            execute_publication(self.conn, 'facebook', EVENT, rejected, self.finalize)
        self.assertEqual(list_attempts(self.conn)[0]['state'], 'failed')
        def timeout():
            begin_remote_mutation("facebook_feed")
            raise httpx.ReadTimeout('https://secret:credential@private.invalid')
        with self.assertRaises(click.ClickException) as error:
            execute_publication(self.conn, 'facebook', EVENT, timeout, self.finalize)
        self.assertNotIn('credential', str(error.exception))
        self.assertEqual(list_attempts(self.conn)[0]['state'], 'publishing')
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
        resolve_attempt(self.conn, attempt['attempt_uuid'], 'published', lambda event, post_id, url: FACEBOOK.remember_post(self.conn, event, post_id, commit=False))
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
                    begin_remote_mutation({"facebook": "facebook_feed", "mastodon": "mastodon_status", "instagram": "instagram_publish"}[platform])
                    return ('123', 'https://example.test/123') if module is MASTODON else '123'
                with patch.object(module, helper, side_effect=remote) as call, patch('click.confirm', return_value=False), \
                     patch.object(INSTAGRAM, 'validate_image', return_value='https://api.kulturbytes.de/image.jpg'):
                    module.publish_event(Mock(), conn, EVENT, dry_run=True)
                    module.publish_event(Mock(), conn, EVENT, dry_run=False)
                    call.assert_not_called()
                    self.assertEqual(list_attempts(conn), [])
                    with patch('click.confirm', return_value=True):
                        module.publish_event(Mock(), conn, EVENT, dry_run=False, config=Mock(page_id="123", user_id="123", base_url="https://example.test"))
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

    def test_content_fingerprint_is_deterministic_and_context_is_minimal(self):
        from kulturbytes_common.publications import content_fingerprint
        text = 'Ein eindeutiger Beitrag mit Umlauten: äöü'
        fingerprint = content_fingerprint('facebook', EVENT, text)
        self.assertEqual(fingerprint, content_fingerprint('FACEBOOK', deepcopy(EVENT), text))
        self.assertNotEqual(fingerprint, content_fingerprint('instagram', EVENT, text))
        self.assertNotEqual(fingerprint, content_fingerprint('facebook', EVENT, text + '!'))
        event = deepcopy(EVENT)
        event['date']['slug'] = 'changed'
        self.assertNotEqual(fingerprint, content_fingerprint('facebook', event, text))
        attempt = reserve_attempt(self.conn, 'facebook', EVENT, message=text, target_ref='123')
        row = get_attempt(self.conn, attempt)
        self.assertEqual(row['content_sha256'], fingerprint)
        self.assertEqual(row['target_ref'], '123')
        self.assertEqual(row['date_slug'], EVENT['date']['slug'])
        self.assertIn('slug', row['event_snapshot'])
        self.assertNotIn(text, str(row))
        self.assertNotIn('Authorization', str(row))

    def test_additive_context_migration_preserves_old_attempts(self):
        from kulturbytes_common.publications import init_journal
        with sqlite3.connect(':memory:') as legacy:
            legacy.execute('''CREATE TABLE publication_attempts (
                attempt_uuid TEXT PRIMARY KEY, platform TEXT, date_uuid TEXT, event_uuid TEXT,
                state TEXT, remote_id TEXT, remote_url TEXT, error_class TEXT, event_snapshot TEXT,
                created_at TEXT, updated_at TEXT)''')
            legacy.execute("INSERT INTO publication_attempts VALUES ('old','facebook','date-1','event-1', 'remote_succeeded','123',NULL,NULL,'{}','2000','2000')")
            init_journal(legacy)
            init_journal(legacy)
            row = get_attempt(legacy, 'old')
            self.assertEqual((row['state'], row['remote_id']), ('remote_succeeded', '123'))
            for field in ('mutation_stage', 'date_slug', 'target_ref', 'content_sha256'):
                self.assertIsNone(row[field])

    def test_recovery_is_one_atomic_transaction_and_rolls_back_all_local_writes(self):
        # Failure at the last update must undo the legacy INSERT and tentative state/ID.
        self.conn.execute("CREATE TRIGGER reject_published BEFORE UPDATE ON publication_attempts WHEN NEW.state='published' BEGIN SELECT RAISE(ABORT, 'final transition failed'); END")
        self.conn.commit()
        attempt = reserve_attempt(self.conn, 'facebook', EVENT)
        def finalize(event, post_id, url):
            FACEBOOK.remember_post(self.conn, event, post_id, commit=False)
        statements = []
        self.conn.set_trace_callback(statements.append)
        with self.assertRaises(sqlite3.IntegrityError):
            resolve_attempt(self.conn, attempt, 'published', finalize, remote_id='123')
        row = get_attempt(self.conn, attempt)
        self.assertEqual((row['state'], row['remote_id']), ('reserved', None))
        self.assertFalse(already_published(self.conn, 'date-1'))
        self.assertEqual(sum(s == 'BEGIN IMMEDIATE' for s in statements), 1)
        self.assertNotIn('COMMIT', statements)
        self.assertIn('ROLLBACK', statements)
        self.assertFalse(self.conn.in_transaction)
        mark_remote_succeeded(self.conn, attempt, '123')
        with self.assertRaises(sqlite3.IntegrityError):
            resolve_attempt(self.conn, attempt, 'published', finalize)
        row = get_attempt(self.conn, attempt)
        self.assertEqual((row['state'], row['remote_id']), ('remote_succeeded', '123'))
        self.assertFalse(already_published(self.conn, 'date-1'))
        self.conn.execute('DROP TRIGGER reject_published')
        self.conn.commit()
        resolve_attempt(self.conn, attempt, 'published', finalize)
        self.assertTrue(already_published(self.conn, 'date-1'))

    def test_recovery_cannot_replace_confirmed_id_or_accept_credential_urls(self):
        attempt = reserve_attempt(self.conn, 'facebook', EVENT)
        for kwargs in ({'remote_id': 'token-value'}, {'remote_id': '123', 'remote_url': 'https://example.test/?access_token=secret'},
                       {'remote_id': '123', 'remote_url': 'https://user:pass@example.test/post'}):
            with self.assertRaises(click.ClickException):
                resolve_attempt(self.conn, attempt, 'published', Mock(), **kwargs)
            self.assertEqual(get_attempt(self.conn, attempt)['state'], 'reserved')
        mark_remote_succeeded(self.conn, attempt, '123')
        for kwargs in ({'remote_id': '456'}, {'remote_url': 'https://example.test/456'}):
            with self.assertRaises(click.ClickException):
                resolve_attempt(self.conn, attempt, 'published', Mock(), **kwargs)
        self.assertEqual(get_attempt(self.conn, attempt)['remote_id'], '123')

    def test_api_rejection_classification_is_method_aware(self):
        from kulturbytes_common.auth import response_payload
        for status in (400, 401, 403, 404, 422, 408, 409, 500, 502, 503, 504):
            for method in ('POST', 'GET'):
                response = httpx.Response(status, json={'error': 'test-secret'},
                                          request=httpx.Request(method, 'https://example.test'))
                with self.assertRaises(click.ClickException) as error:
                    response_payload(response, 'Facebook', 'test-secret')
                self.assertEqual(isinstance(error.exception, RemoteRejected),
                                 method == 'POST' and status in (400, 401, 403, 404, 422))
                self.assertNotIn('test-secret', str(error.exception))

    def test_each_mutation_stage_and_actual_content_are_durable_before_post(self):
        from kulturbytes_common.publications import content_fingerprint
        from urllib.parse import parse_qs
        configs = {
            FACEBOOK: FACEBOOK.FacebookConfig('123', 'never-store-token', 'v26.0'),
            MASTODON: MASTODON.MastodonConfig('https://example.test', 'never-store-token'),
            INSTAGRAM: INSTAGRAM.InstagramConfig('123', 'never-store-token', 'https://example.test/v26.0'),
        }
        for module, config in configs.items():
            platform = module.__name__.split('.')[0].removeprefix('kulturbytes_')
            for with_image in ((False, True) if module is not INSTAGRAM else (True,)):
                db = Path(self.directory.name) / f'{platform}-stages-{with_image}.db'
                event = deepcopy(EVENT)
                if with_image:
                    event['images'] = {'main': {'url': 'https://api.kulturbytes.de/image.jpg'}}
                stages = []
                def respond(request):
                    if request.method == 'GET':
                        if '/image' in request.url.path:
                            return httpx.Response(200, content=b'\xff\xd8\xffjpeg')
                        return httpx.Response(200, json={'url': 'https://api.kulturbytes.de/image.jpg', 'status_code': 'FINISHED'})
                    with sqlite3.connect(db) as observer:
                        row = list_attempts(observer)[0]
                    stage = {'/api/v2/media': 'mastodon_media', '/api/v1/statuses': 'mastodon_status',
                             '/v26.0/123/photos': 'facebook_photo', '/v26.0/123/feed': 'facebook_feed',
                             '/v26.0/123/media': 'instagram_container', '/v26.0/123/media_publish': 'instagram_publish'}[request.url.path]
                    self.assertEqual(row['mutation_stage'], stage)
                    self.assertEqual(row['state'], 'publishing')
                    stages.append(stage)
                    if module is FACEBOOK:
                        message = FACEBOOK.build_message(event)
                        if with_image:
                            self.assertIn(message.encode(), request.content)
                        else:
                            self.assertEqual(parse_qs(request.content.decode())['message'][0], message)
                    elif module is MASTODON:
                        message = MASTODON.build_mastodon_message(event)
                        if stage == 'mastodon_status':
                            self.assertEqual(parse_qs(request.content.decode())['status'][0], message)
                    else:
                        message = INSTAGRAM.build_instagram_caption(event)
                        if stage == 'instagram_container':
                            self.assertEqual(parse_qs(request.content.decode())['caption'][0], message)
                    self.assertEqual(row['content_sha256'], content_fingerprint(platform, event, message))
                    self.assertEqual(row['target_ref'], 'https://example.test' if module is MASTODON else '123')
                    self.assertNotIn('never-store-token', str(row))
                    return httpx.Response(200, json={'id': '123', 'url': 'https://example.test/123'})
                with self.subTest(platform=platform, image=with_image), patch.object(module, 'DATABASE_PATH', db), \
                     httpx.Client(transport=httpx.MockTransport(respond)) as client, patch('click.confirm', return_value=True):
                    conn = module.init_database()
                    self.addCleanup(conn.close)
                    module.publish_event(client, conn, event, False, config=config)
                    expected = {'facebook': ['facebook_photo' if with_image else 'facebook_feed'],
                                'mastodon': (['mastodon_media'] if with_image else []) + ['mastodon_status'],
                                'instagram': ['instagram_container', 'instagram_publish']}[platform]
                    self.assertEqual(stages, expected)
                    self.assertEqual(list_attempts(conn)[0]['mutation_stage'], expected[-1])

    def test_uncertain_instagram_final_post_keeps_publish_stage_and_remote_success_is_durable(self):
        config = INSTAGRAM.InstagramConfig('123', 'test-secret', 'https://example.test/v26.0')
        event = deepcopy(EVENT)
        event['images'] = {'main': {'url': 'https://api.kulturbytes.de/image.jpg'}}
        for failure in ('timeout', 'reset', '503'):
            db = Path(self.directory.name) / f'instagram-final-{failure}.db'
            posts = []
            def respond(request):
                if request.url.path.endswith('/media_publish'):
                    posts.append(request)
                    if failure == 'timeout':
                        raise httpx.ReadTimeout('test-secret')
                    if failure == 'reset':
                        raise httpx.ReadError('test-secret')
                    return httpx.Response(503, json={'error': 'test-secret'})
                if request.url.path == '/image.jpg':
                    return httpx.Response(200, content=b'\xff\xd8\xffjpeg')
                return httpx.Response(200, json={'id': '123', 'status_code': 'FINISHED'})
            with patch.object(INSTAGRAM, 'DATABASE_PATH', db), httpx.Client(transport=httpx.MockTransport(respond)) as client, \
                 patch('click.confirm', return_value=True):
                conn = INSTAGRAM.init_database()
                self.addCleanup(conn.close)
                with self.assertRaises(click.ClickException) as error:
                    INSTAGRAM.publish_event(client, conn, event, False, config=config)
                row = list_attempts(conn)[0]
                self.assertEqual((row['state'], row['mutation_stage']), ('publishing', 'instagram_publish'))
                self.assertIsNotNone(row['error_class'])
                self.assertNotIn('test-secret', str(row) + str(error.exception))
                self.assertEqual(len(posts), 1)
                with self.assertRaises(click.ClickException):
                    reserve_attempt(conn, 'instagram', event, allow_repeat=True)

    def test_live_finalization_rollback_keeps_the_previously_committed_remote_success(self):
        self.conn.execute("CREATE TRIGGER reject_final_state BEFORE UPDATE ON publication_attempts WHEN NEW.state='published' BEGIN SELECT RAISE(ABORT, 'final state failure'); END")
        self.conn.commit()
        with self.assertRaises(click.ClickException):
            execute_publication(self.conn, 'facebook', EVENT, self.publish, self.finalize)
        row = list_attempts(self.conn)[0]
        self.assertEqual((row['state'], row['remote_id'], row['mutation_stage']),
                         ('remote_succeeded', '123', 'facebook_feed'))
        self.assertFalse(already_published(self.conn, 'date-1'))
        self.assertFalse(self.conn.in_transaction)
