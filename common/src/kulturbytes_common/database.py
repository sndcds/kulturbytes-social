import os
import sqlite3
from pathlib import Path


def already_published(conn: sqlite3.Connection, date_uuid: str) -> bool:
    """Prüft einen Termin unabhängig von der plattformspezifischen Post-ID."""
    return conn.execute(
        "SELECT 1 FROM published_events WHERE date_uuid = ?",
        (date_uuid,),
    ).fetchone() is not None


def get_database_path(platform: str) -> Path:
    """Use existing checkout state, or a stable user data directory when installed."""
    checkout = Path(__file__).resolve().parents[3]
    if (checkout / "pyproject.toml").is_file() and (checkout / "common/src/kulturbytes_common").is_dir():
        directory = checkout / platform
    else:
        data_home = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local/share")
        if not data_home.is_absolute():
            data_home = Path.home() / ".local/share"
        directory = data_home / "kulturbytes-social"
    configured = os.getenv("DATABASE_PATH")
    path = Path(configured).expanduser() if configured else Path(f"{platform}_posts.sqlite3")
    return path if path.is_absolute() else directory / path
