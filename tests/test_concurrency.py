import sqlite3
from copy import deepcopy
from unittest.mock import patch
from pathlib import Path
import tempfile

import click
from dotenv_support import IsolatedEnvironmentTestCase
from kulturbytes_common.publications import reserve_attempt, mark_failed, mark_remote_succeeded, mark_published
from test_publishers import EVENT, FACEBOOK, MASTODON


class ConcurrencyTests(IsolatedEnvironmentTestCase):
    def test_independent_connections_contend_but_other_dates_and_platforms_work(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(FACEBOOK, 'DATABASE_PATH', Path(directory) / 'facebook.db'), \
             patch.object(MASTODON, 'DATABASE_PATH', Path(directory) / 'mastodon.db'):
            a, b, other = FACEBOOK.init_database(), FACEBOOK.init_database(), MASTODON.init_database()
            try:
                first = reserve_attempt(a, 'facebook', EVENT)
                with self.assertRaises(click.ClickException):
                    reserve_attempt(b, 'facebook', EVENT, allow_repeat=True)
                reserve_attempt(other, 'mastodon', EVENT)
                another_date = deepcopy(EVENT)
                another_date['date']['uuid'] = 'different-date'
                reserve_attempt(b, 'facebook', another_date)
                mark_failed(a, first, 'BeforeRemoteRequest')
                second = reserve_attempt(b, 'facebook', EVENT)
                mark_remote_succeeded(b, second, '123')
                with self.assertRaises(click.ClickException):
                    reserve_attempt(a, 'facebook', EVENT, allow_repeat=True)
                FACEBOOK.remember_post(b, EVENT, '123')
                mark_published(b, second)
                with self.assertRaises(click.ClickException):
                    reserve_attempt(a, 'facebook', EVENT)
                reserve_attempt(a, 'facebook', EVENT, allow_repeat=True)
            finally:
                a.close()
                b.close()
                other.close()

    def test_busy_database_prevents_reservation_before_any_remote_work(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(FACEBOOK, 'DATABASE_PATH', Path(directory) / 'facebook.db'):
            a, b = FACEBOOK.init_database(), FACEBOOK.init_database()
            try:
                self.assertEqual(b.execute('PRAGMA busy_timeout').fetchone()[0], 5000)
                b.execute('PRAGMA busy_timeout=0')  # deterministic contention without sleeping
                a.execute('BEGIN IMMEDIATE')
                with self.assertRaises(sqlite3.OperationalError):
                    reserve_attempt(b, 'facebook', EVENT)
                a.rollback()
                reserve_attempt(b, 'facebook', EVENT)
            finally:
                a.close()
                b.close()
