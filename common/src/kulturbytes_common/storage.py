"""Neutral publication-state interface; historical schema details remain private."""

from .database import already_published as already_published
from .legacy_storage import init_database as init_database
from .legacy_storage import item_key as item_key
from .legacy_storage import remember_post as remember_post


def unresolved_message(conn, publication_key: str) -> str | None:
    from .publications import unresolved_attempt

    attempt = unresolved_attempt(conn, publication_key)
    if attempt is None:
        return None
    return (
        f"Inhalt ist reserviert oder ungeklärt: Schlüssel={publication_key}, "
        f"Status={attempt['state']}, Versuch={attempt['attempt_uuid']}, "
        f"Remote-ID={attempt.get('remote_id') or 'unbekannt'}, SHA256={attempt.get('content_sha256') or 'unbekannt'}. "
        "Mit kulturbytes-social attempts prüfen und auflösen."
    )


__all__ = [
    "already_published",
    "init_database",
    "item_key",
    "remember_post",
    "unresolved_message",
]
