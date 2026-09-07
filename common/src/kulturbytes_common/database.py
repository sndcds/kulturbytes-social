import sqlite3


def already_published(conn: sqlite3.Connection, date_uuid: str) -> bool:
    """Prüft einen Termin unabhängig von der plattformspezifischen Post-ID."""
    return conn.execute(
        "SELECT 1 FROM published_events WHERE date_uuid = ?",
        (date_uuid,),
    ).fetchone() is not None
