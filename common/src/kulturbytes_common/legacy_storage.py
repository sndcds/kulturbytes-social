"""Existing publication schema, fed by canonical items or saved recovery snapshots."""

import sqlite3

import click

from .database import get_database_path, open_database
from .sources.models import ContentItem

COLUMNS = {
    "facebook": "facebook_post_id",
    "instagram": "instagram_media_id",
    "mastodon": "mastodon_status_id",
}


def record_for(item: ContentItem | dict) -> dict:
    if isinstance(item, dict):
        # Historical recovery snapshots use this internal format; never source extraction.
        return item
    identity = item._source_context.identity if item._source_context else None
    if identity is None or item.id is None:
        raise click.ClickException(
            "Veröffentlichung benötigt eine stabile Quellen-ID (fields.id)."
        )
    return {
        "uuid": identity.content_key,
        "title": item.title,
        "date": {
            "uuid": identity.publication_key,
            "slug": identity.revision,
            "start_date": item.date or "",
            "start_time": item.time,
        },
    }


def item_key(item: ContentItem) -> str:
    return item._source_context.identity.publication_key if item._source_context else ""


def init_database(platform: str, override=None) -> sqlite3.Connection:
    from .publications import init_journal

    column = COLUMNS[platform]
    conn = open_database(override or get_database_path(platform), platform)
    extra = "mastodon_status_url TEXT," if platform == "mastodon" else ""
    conn.execute(f"""CREATE TABLE IF NOT EXISTS published_events (
        date_uuid TEXT PRIMARY KEY, event_uuid TEXT NOT NULL,
        {column} TEXT NOT NULL, {extra} title TEXT NOT NULL,
        start_date TEXT NOT NULL, start_time TEXT, published_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    init_journal(conn)
    conn.commit()
    return conn


def remember_post(
    conn: sqlite3.Connection,
    item: ContentItem | dict,
    remote_id: str,
    remote_url: str | None = None,
    *,
    platform: str,
    commit: bool = True,
) -> None:
    snapshot = record_for(item)
    stamp = snapshot["date"]
    columns = [
        "date_uuid",
        "event_uuid",
        COLUMNS[platform],
        "title",
        "start_date",
        "start_time",
    ]
    values = [
        stamp["uuid"],
        snapshot["uuid"],
        remote_id,
        snapshot["title"],
        stamp["start_date"],
        stamp.get("start_time"),
    ]
    if platform == "mastodon":
        columns.append("mastodon_status_url")
        values.append(remote_url)
    updates = ",".join(f"{column}=excluded.{column}" for column in columns[1:])
    conn.execute(
        f"""INSERT INTO published_events ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})
        ON CONFLICT(date_uuid) DO UPDATE SET {updates},published_at=CURRENT_TIMESTAMP""",
        values,
    )
    if commit:
        conn.commit()
