import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import click
from dotenv_support import IsolatedEnvironmentTestCase
from test_instagram import instagram
from test_publishers import FACEBOOK, MASTODON

from kulturbytes_common import database, environment


class DatabasePathTests(IsolatedEnvironmentTestCase):
    def test_platform_precedence(self):
        for platform in database.PLATFORM_COLUMNS:
            name = platform.upper() + "_DATABASE_PATH"
            with patch.dict(
                os.environ,
                {name: "env.sqlite3", "DATABASE_PATH": "/tmp/legacy.sqlite3"},
                clear=True,
            ):
                environment.get_env_file_path().write_text(f"{name}=local.sqlite3\n")
                self.assertEqual(
                    database.get_database_path(platform).name, "local.sqlite3"
                )
                environment.get_env_file_path().write_text("")
                self.assertEqual(
                    database.get_database_path(platform).name, "env.sqlite3"
                )
                with patch.dict(os.environ, {name: "/tmp/specific.sqlite3"}):
                    self.assertEqual(
                        database.get_database_path(platform),
                        Path("/tmp/specific.sqlite3"),
                    )

    def test_same_file_cannot_accept_different_platform_schemas(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared.sqlite3"
            with patch.object(FACEBOOK, "DATABASE_PATH", path):
                FACEBOOK.init_database().close()
            for module in (MASTODON, instagram):
                with (
                    patch.object(module, "DATABASE_PATH", path),
                    self.assertRaises(click.ClickException),
                ):
                    module.init_database()
            with sqlite3.connect(path) as conn:
                self.assertEqual(
                    conn.execute("SELECT platform FROM publisher_metadata").fetchone(),
                    ("facebook",),
                )

    def test_legacy_schema_is_checked_before_metadata_is_written(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            with sqlite3.connect(path) as conn:
                conn.execute(
                    "CREATE TABLE published_events (date_uuid TEXT PRIMARY KEY, facebook_post_id TEXT)"
                )
                conn.execute("INSERT INTO published_events VALUES ('date-1', 'post-1')")
            with self.assertRaises(click.ClickException):
                database.open_database(path, "mastodon")
            with database.open_database(path, "facebook") as conn:
                self.assertEqual(
                    conn.execute("SELECT * FROM published_events").fetchall(),
                    [("date-1", "post-1")],
                )
                self.assertEqual(
                    conn.execute("PRAGMA busy_timeout").fetchone(), (5000,)
                )

    def test_legacy_dotenv_fallback_warns_only_once_and_specific_key_wins(self):
        environment.get_env_file_path().write_text(
            "DATABASE_PATH=/tmp/legacy-state.db\n"
        )
        database._warn_legacy_database_path.cache_clear()
        self.addCleanup(database._warn_legacy_database_path.cache_clear)
        with patch.dict(os.environ, {}, clear=True), patch("click.echo") as echo:
            for platform in database.PLATFORM_COLUMNS:
                self.assertEqual(
                    database.get_database_path(platform), Path("/tmp/legacy-state.db")
                )
            echo.assert_called_once()
            with patch.dict(
                os.environ, {"MASTODON_DATABASE_PATH": "/tmp/mastodon-state.db"}
            ):
                self.assertEqual(
                    database.get_database_path("mastodon"),
                    Path("/tmp/mastodon-state.db"),
                )
