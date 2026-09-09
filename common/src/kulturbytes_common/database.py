import os
import sqlite3
from functools import cache
from pathlib import Path

import click

from .environment import get_config

PLATFORM_COLUMNS = {
    "bluesky": "bluesky_post_uri",
    "facebook": "facebook_post_id",
    "instagram": "instagram_media_id",
    "mastodon": "mastodon_status_id",
}


@cache
def _warn_legacy_database_path() -> None:
    """Emit the deprecated fallback warning once per process, across platforms."""
    click.echo(
        "DATABASE_PATH ist veraltet; verwende separate <PLATFORM>_DATABASE_PATH-Werte.",
        err=True,
    )


def already_published(conn: sqlite3.Connection, date_uuid: str) -> bool:
    """Prüft einen Termin unabhängig von der plattformspezifischen Post-ID."""
    return (
        conn.execute(
            "SELECT 1 FROM published_events WHERE date_uuid = ?",
            (date_uuid,),
        ).fetchone()
        is not None
    )


def get_database_path(platform: str) -> Path:
    """Use existing checkout state, or a stable user data directory when installed."""
    checkout = Path(__file__).resolve().parents[3]
    if (checkout / "pyproject.toml").is_file() and (
        checkout / "common/src/kulturbytes_common"
    ).is_dir():
        directory = checkout / platform
    else:
        data_home = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local/share")
        if not data_home.is_absolute():
            data_home = Path.home() / ".local/share"
        directory = data_home / "kulturbytes-social"
    configured = get_config(f"{platform.upper()}_DATABASE_PATH")
    if not configured:
        configured = get_config("DATABASE_PATH")
        if configured:
            _warn_legacy_database_path()
    path = (
        Path(configured).expanduser()
        if configured
        else Path(f"{platform}_posts.sqlite3")
    )
    return path if path.is_absolute() else directory / path


def open_database(path: Path, platform: str) -> sqlite3.Connection:
    """Claim a database before creating platform tables; preserve compatible legacy data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(published_events)")
        }
        if columns and (
            PLATFORM_COLUMNS[platform] not in columns
            or any(
                column in columns
                for other, column in PLATFORM_COLUMNS.items()
                if other != platform
            )
        ):
            raise click.ClickException(
                "Datenbankschema gehört zu einer anderen Plattform; separaten Datenbankpfad konfigurieren."
            )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS publisher_metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), platform TEXT NOT NULL)"
        )
        owner = conn.execute(
            "SELECT platform FROM publisher_metadata WHERE singleton=1"
        ).fetchone()
        if owner and owner[0] != platform:
            raise click.ClickException(
                "Datenbank ist bereits einer anderen Plattform zugeordnet; separaten Pfad konfigurieren."
            )
        conn.execute(
            "INSERT OR IGNORE INTO publisher_metadata VALUES (1, ?)", (platform,)
        )
        # Caller creates its legacy table and commits while still holding the schema lock.
        return conn
    except Exception:
        conn.rollback()
        conn.close()
        raise
