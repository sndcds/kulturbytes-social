from copy import deepcopy
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
from click.testing import CliRunner
from dotenv_support import IsolatedEnvironmentTestCase
from kulturbytes_common.publications import reserve_attempt, mark_failed, mark_remote_succeeded, mark_published, list_attempts
from kulturbytes_social.cli import cli
from test_publishers import FACEBOOK, EVENT


class AttemptsCLITests(IsolatedEnvironmentTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'attempts.sqlite3'
        setting = patch.object(FACEBOOK, 'DATABASE_PATH', self.path)
        setting.start()
        self.addCleanup(setting.stop)
        self.conn = FACEBOOK.init_database()
        self.addCleanup(self.conn.close)
        self.attempts = []
        # Identical timestamps exercise deterministic newest-first rowid tie breaking.
        for index, state in enumerate(('reserved', 'failed', 'publishing', 'published', 'remote_succeeded')):
            event = deepcopy(EVENT)
            event['date']['uuid'] = f'date-{index}'
            attempt = reserve_attempt(self.conn, 'facebook', event)
            self.attempts.append(attempt)
            if state == 'failed':
                mark_failed(self.conn, attempt, 'TestRejection')
            elif state == 'publishing':
                self.conn.execute("UPDATE publication_attempts SET state='publishing' WHERE attempt_uuid=?", (attempt,))
                self.conn.commit()
            elif state in ('published', 'remote_succeeded'):
                mark_remote_succeeded(self.conn, attempt, '123')
                if state == 'published':
                    mark_published(self.conn, attempt)
        self.conn.execute("UPDATE publication_attempts SET created_at='2020-01-01 00:00:00'")
        self.conn.commit()

    def invoke(self, *args, expected=0):
        before = list_attempts(self.conn, limit=0)
        with patch.object(httpx.Client, 'send', side_effect=AssertionError('No network allowed')), \
             patch('kulturbytes_common.credentials.resolve_credential', side_effect=AssertionError('No credentials allowed')), \
             patch('kulturbytes_common.credentials.get_secret', side_effect=AssertionError('No keyring allowed')), \
             patch.object(FACEBOOK, 'load_config', side_effect=AssertionError('No auth config allowed')):
            result = CliRunner().invoke(cli, ['attempts', 'list', '--platform', 'facebook', *args])
        self.assertEqual(result.exit_code, expected, result.output + str(result.exception))
        self.assertEqual(list_attempts(self.conn, limit=0), before)
        return result.output

    def test_default_newest_first_and_limit(self):
        output = self.invoke()
        positions = [output.index(attempt) for attempt in reversed(self.attempts)]
        self.assertEqual(positions, sorted(positions))
        output = self.invoke('--limit', '2')
        self.assertIn(self.attempts[4], output)
        self.assertIn(self.attempts[3], output)
        self.assertNotIn(self.attempts[2], output)
        self.assertEqual(self.invoke('--limit', '0'), self.invoke())
        self.invoke('--limit', '-1', expected=2)

    def test_active_state_and_date_filters(self):
        output = self.invoke('--active')
        for index in (0, 2, 4):
            self.assertIn(self.attempts[index], output)
        for index in (1, 3):
            self.assertNotIn(self.attempts[index], output)
        output = self.invoke('--state', 'remote_succeeded')
        self.assertIn(self.attempts[4], output)
        self.assertNotIn(self.attempts[0], output)
        output = self.invoke('--date-uuid', 'date-1')
        self.assertIn(self.attempts[1], output)
        self.assertNotIn(self.attempts[2], output)
        self.assertIn('Keine Veröffentlichungsversuche', self.invoke('--date-uuid', 'unknown'))
        self.assertIn(self.attempts[4], self.invoke('--active', '--state', 'remote_succeeded'))
        self.invoke('--active', '--state', 'published', expected=1)

    def test_query_applies_filters_and_limits_in_sql(self):
        queries = []
        self.conn.set_trace_callback(queries.append)
        rows = list_attempts(self.conn, state='failed', date_uuid='date-1', limit=1)
        self.assertEqual([row['attempt_uuid'] for row in rows], [self.attempts[1]])
        self.assertIn('WHERE', queries[0])
        self.assertIn('LIMIT 1', queries[0])
        # Parameter binding treats SQL-looking identifiers as literal values.
        self.assertEqual(list_attempts(self.conn, date_uuid="' OR 1=1 --"), [])
