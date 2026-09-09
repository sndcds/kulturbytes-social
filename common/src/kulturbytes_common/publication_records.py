"""Canonical-to-legacy snapshot conversion shared by storage and the journal."""

import click

from .sources.models import ContentItem


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
