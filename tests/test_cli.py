import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import chdir
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
from dotenv_support import IsolatedEnvironmentTestCase

from kulturbytes_common import database
from kulturbytes_social.cli import cli

ROOT = Path(__file__).resolve().parents[1]


class UnifiedCliTests(IsolatedEnvironmentTestCase):
    def test_root_help_and_unknown_command(self):
        result = CliRunner().invoke(cli, ["--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        for platform in ["facebook", "mastodon", "instagram"]:
            self.assertIn(platform, result.output)
            help_result = CliRunner().invoke(cli, [platform, "--help"])
            self.assertEqual(help_result.exit_code, 0, help_result.output)
            for option in [
                "--dry-run",
                "--publish",
                "--check-auth",
                "--credentials",
                "--event-uuid",
                "--date-identifier",
                "--city",
                "--limit",
                "--include-published",
            ]:
                self.assertIn(option, help_result.output)
        self.assertEqual(CliRunner().invoke(cli, ["unknown"]).exit_code, 2)

    def test_only_root_executable_and_no_wrappers(self):
        root = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual(
            root["project"]["scripts"],
            {"kulturbytes-social": "kulturbytes_social.cli:cli"},
        )
        for platform in ["facebook", "mastodon", "instagram"]:
            project = tomllib.loads((ROOT / platform / "pyproject.toml").read_text())
            self.assertNotIn("scripts", project["project"])
            self.assertFalse((ROOT / platform / "main.py").exists())

    def test_installed_entry_point_outside_checkout(self):
        executable = Path(sys.executable).parent / "kulturbytes-social"
        with tempfile.TemporaryDirectory() as directory:
            for args in [[], ["facebook"], ["mastodon"], ["instagram"]]:
                result = subprocess.run(
                    [str(executable), *args, "--help"],
                    cwd=directory,
                    env={},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("kulturbytes-social", result.stdout)
                self.assertFalse(list(Path(directory).iterdir()))

    def test_checkout_database_paths_are_cwd_independent(self):
        with patch.dict(os.environ, {}, clear=True):
            before = {
                platform: database.get_database_path(platform)
                for platform in ["facebook", "mastodon", "instagram"]
            }
            with tempfile.TemporaryDirectory() as directory, chdir(directory):
                for platform, path in before.items():
                    self.assertEqual(database.get_database_path(platform), path)
                    self.assertEqual(
                        path, ROOT / platform / f"{platform}_posts.sqlite3"
                    )
            with patch.dict(os.environ, {"DATABASE_PATH": "custom.sqlite3"}):
                self.assertEqual(
                    database.get_database_path("facebook"),
                    ROOT / "facebook/custom.sqlite3",
                )
            with patch.dict(os.environ, {"DATABASE_PATH": "/absolute/custom.sqlite3"}):
                self.assertEqual(
                    database.get_database_path("facebook"),
                    Path("/absolute/custom.sqlite3"),
                )

    def test_installed_database_defaults_use_user_data(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            source = (
                home
                / "venv/lib/python3.12/site-packages/kulturbytes_common/database.py"
            )
            with (
                patch.object(database, "__file__", str(source)),
                patch.object(Path, "home", return_value=home),
            ):
                with patch.dict(os.environ, {}, clear=True):
                    expected = (
                        home / ".local/share/kulturbytes-social/mastodon_posts.sqlite3"
                    )
                    self.assertEqual(database.get_database_path("mastodon"), expected)
                with patch.dict(
                    os.environ, {"XDG_DATA_HOME": str(home / "data")}, clear=True
                ):
                    self.assertEqual(
                        database.get_database_path("instagram"),
                        home / "data/kulturbytes-social/instagram_posts.sqlite3",
                    )
                with patch.dict(os.environ, {"XDG_DATA_HOME": "relative"}, clear=True):
                    self.assertEqual(database.get_database_path("mastodon"), expected)
            # Resolving paths must not create state, including during help/import.
            self.assertFalse(list(home.iterdir()))


if __name__ == "__main__":
    unittest.main()
