"""Real PostgreSQL tests. Only an explicitly configured *_test database is touched."""
import os
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from dotenv_support import IsolatedEnvironmentTestCase
from kulturbytes_social.db.session import database_engine, session_factory
from kulturbytes_social.db.repositories.publications import PublicationRepository

TEST_URL = os.environ.get('TEST_DATABASE_URL')
ROOT = Path(__file__).resolve().parents[1]


def test_engine():
    if not TEST_URL:
        import unittest
        raise unittest.SkipTest('TEST_DATABASE_URL is required for real PostgreSQL integration tests')
    url = make_url(TEST_URL)
    if url.drivername != 'postgresql+psycopg' or not url.database or not url.database.endswith('_test'):
        raise RuntimeError('TEST_DATABASE_URL must use PostgreSQL and a dedicated database ending in _test')
    return database_engine(TEST_URL)


def migrate(engine, revision='head'):
    config = Config(str(ROOT / 'alembic.ini'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, revision)


class PostgreSQLTestCase(IsolatedEnvironmentTestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = test_engine()
        migrate(cls.engine)
        cls.factory = session_factory(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text('TRUNCATE publications, publication_attempts, jobs'))
        self.repo = PublicationRepository(self.factory)
