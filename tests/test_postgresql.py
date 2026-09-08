"""Persistence, cross-connection contention and recovery on an actual server."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import threading
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import event as sql_event, inspect, text
from sqlalchemy.exc import IntegrityError
from kulturbytes_common.errors import AlreadyPublished, DatabaseUnavailable, PublicationConflict
from kulturbytes_common.publications import content_fingerprint
from kulturbytes_social.db.models import Attempt, Job, Publication, now
from kulturbytes_social.db.repositories.publications import PublicationRepository
from kulturbytes_social.db.repositories.jobs import JobRepository
from kulturbytes_social.db.session import session_factory
from postgres_support import PostgreSQLTestCase, test_engine, migrate
from test_publishers import EVENT


class PostgreSQLTests(PostgreSQLTestCase):
    def reserve(self, repo=None, platform='facebook', event=None, repeat=False):
        return (repo or self.repo).reserve(platform=platform, event=event or EVENT,
            target_ref='123', fingerprint='a' * 64, force_repeat=repeat)

    def succeed(self, attempt):
        self.repo.transition(attempt['id'], 'remote_succeeded', ('reserved',), remote_id='456')
        return self.repo.finalize(attempt['id'])

    def test_migration_is_repeatable_and_uses_native_types(self):
        migrate(self.engine)
        self.repo.readiness()
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text('SELECT version_num FROM alembic_version')), '0001_postgresql')
            types = dict(connection.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='jobs'" )).all())
            self.assertEqual(types['id'], 'uuid')
            self.assertEqual(types['payload'], 'jsonb')
            self.assertEqual(types['created_at'], 'timestamp with time zone')
        self.assertEqual(set(inspect(self.engine).get_table_names()), {'alembic_version', 'publications', 'publication_attempts', 'jobs'})

    def test_independent_connections_reserve_one_winner(self):
        barrier = threading.Barrier(2)
        def contender():
            engine = test_engine()
            try:
                repository = PublicationRepository(session_factory(engine))
                barrier.wait(timeout=5)
                try:
                    return self.reserve(repository)['state']
                except PublicationConflict:
                    return 'conflict'
            finally:
                engine.dispose()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(contender) for _ in range(2)]
            self.assertCountEqual([f.result(timeout=10) for f in futures], ['reserved', 'conflict'])
        self.assertEqual(len(self.repo.attempts()), 1)
        self.reserve(platform='instagram')
        other = deepcopy(EVENT); other['date']['uuid'] = 'date-2'
        self.reserve(event=other)
        self.assertEqual(len(self.repo.attempts()), 3)

    def test_partial_unique_index_is_final_defense(self):
        self.reserve()
        with self.assertRaises(IntegrityError), self.factory.begin() as session:
            session.add(Attempt(platform='facebook', event_uuid='different', date_uuid=EVENT['date']['uuid'], date_slug='different', target_ref='123', content_sha256='b' * 64))
            session.flush()
        self.assertEqual(len(self.repo.attempts()), 1)

    def test_repeat_requires_explicit_flag_and_preserves_history(self):
        first = self.succeed(self.reserve())
        with self.assertRaises(AlreadyPublished):
            self.reserve()
        second = self.succeed(self.reserve(repeat=True))
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(len(self.repo.publications()), 2)
        self.assertEqual(self.repo.publication(first['id'])['remote_id'], '456')

    def test_all_active_states_block_even_force_repeat(self):
        attempt = self.reserve()
        for state in ('reserved', 'publishing', 'remote_succeeded'):
            if state != 'reserved':
                self.repo.transition(attempt['id'], state, ('reserved', 'publishing'), remote_id='456')
            with self.subTest(state=state), self.assertRaises(PublicationConflict):
                self.reserve(repeat=True)

    def test_failed_and_cancelled_allow_fresh_reservation(self):
        for state in ('failed', 'cancelled'):
            attempt = self.reserve()
            result = self.repo.transition(attempt['id'], state, ('reserved',))
            self.assertIsNotNone(result['finished_at'].tzinfo)
            self.assertEqual(result['finished_at'].utcoffset(), timedelta(0))
        self.reserve()

    def test_filters_limits_and_order_are_applied_in_sql(self):
        first = self.reserve()
        self.repo.transition(first['id'], 'failed', ('reserved',))
        last = self.reserve()
        statements = []
        def capture(connection, cursor, statement, parameters, context, many):
            statements.append(statement)
        sql_event.listen(self.engine, 'before_cursor_execute', capture)
        try:
            rows = self.repo.attempts(platform='facebook', date_uuid='date-1', active=True, limit=1)
        finally:
            sql_event.remove(self.engine, 'before_cursor_execute', capture)
        self.assertEqual([r['id'] for r in rows], [last['id']])
        self.assertIn('WHERE', statements[0]); self.assertIn('LIMIT', statements[0]); self.assertIn('ORDER BY', statements[0])
        self.assertEqual(len(self.repo.attempts(limit=0)), 2)
        self.assertEqual(self.repo.attempts(state='failed')[0]['id'], first['id'])

    def test_finalization_failure_rolls_back_both_tables(self):
        attempt = self.reserve()
        self.repo.transition(attempt['id'], 'remote_succeeded', ('reserved',), remote_id='456')
        def fail(mapper, connection, target):
            raise RuntimeError('injected finalization failure')
        sql_event.listen(Publication, 'after_insert', fail)
        try:
            with self.assertRaises(RuntimeError):
                self.repo.finalize(attempt['id'])
        finally:
            sql_event.remove(Publication, 'after_insert', fail)
        self.assertEqual(self.repo.publications(), [])
        engine = test_engine()
        try:
            restarted = PublicationRepository(session_factory(engine))
            row = restarted.attempt(attempt['id'])
            self.assertEqual((row['state'], row['remote_id']), ('remote_succeeded', '456'))
            restarted.finalize(attempt['id'])
        finally:
            engine.dispose()
        self.assertEqual(self.repo.attempt(attempt['id'])['state'], 'published')

    def test_recovery_cannot_replace_confirmed_reference(self):
        attempt = self.reserve()
        self.repo.transition(attempt['id'], 'remote_succeeded', ('reserved',), remote_id='456')
        with self.assertRaises(PublicationConflict):
            self.repo.finalize(attempt['id'], resolve_id='999')
        self.assertEqual(self.repo.attempt(attempt['id'])['remote_id'], '456')
        self.assertEqual(self.repo.publications(), [])

    def test_job_lifecycle_and_json_roundtrip(self):
        jobs = JobRepository(self.factory)
        job = jobs.create({'platform': 'facebook', 'event_uuid': 'event-1'})
        self.assertEqual(job['state'], 'queued')
        jobs.update(job['id'], 'running')
        result = jobs.update(job['id'], 'succeeded', result={'remote_id': '456'})
        self.assertEqual(result['result'], {'remote_id': '456'})
        with self.assertRaises(PublicationConflict):
            jobs.update(job['id'], 'running')
        self.assertEqual(len(jobs.list(limit=0)), 1)

    def test_database_failure_is_sanitized(self):
        with patch.object(self.factory, 'begin', side_effect=IntegrityError('secret-dsn', {}, Exception('password'))):
            with self.assertRaises(DatabaseUnavailable) as error:
                self.repo.known_dates('facebook')
        self.assertNotIn('password', str(error.exception)); self.assertNotIn('secret-dsn', str(error.exception))
