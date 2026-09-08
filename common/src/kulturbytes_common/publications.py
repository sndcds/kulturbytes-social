"""Durable attempts and atomic per-platform/date reservations, without POST retries."""
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
import json
import hashlib
import re
from urllib.parse import urlsplit
import sqlite3
from uuid import uuid4

import click

ACTIVE = ('reserved', 'publishing', 'remote_succeeded')
STATES = (*ACTIVE, 'published', 'failed')
MUTATION_STAGES = frozenset({
    'facebook_photo', 'facebook_feed', 'mastodon_media', 'mastodon_status',
    'instagram_container', 'instagram_publish',
})
_current: ContextVar[tuple[sqlite3.Connection, str] | None] = ContextVar('publication_attempt', default=None)


class RemoteRejected(click.ClickException):
    """A definitive API rejection, as opposed to an uncertain transport failure."""


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Service-level owner; helpers and finalizers inside must not commit."""
    if conn.in_transaction:
        raise click.ClickException('Unerwartete laufende Datenbanktransaktion; Vorgang abgebrochen.')
    try:
        conn.execute('BEGIN IMMEDIATE')
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def content_fingerprint(platform: str, event: dict, message: str) -> str:
    material = {'platform': platform.lower(), 'event_uuid': event['uuid'],
                'date_uuid': event['date']['uuid'], 'date_slug': event['date']['slug'],
                'message': message}
    return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def validate_target_ref(platform: str, value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= 200:
        raise click.ClickException('Ungültige Zielkennung für das Veröffentlichungsjournal.')
    if platform in ('facebook', 'instagram'):
        if not re.fullmatch(r'[0-9]{1,100}', value):
            raise click.ClickException('Zielkennung muss eine numerische Konto-ID sein.')
        return value
    try:
        parsed = urlsplit(value)
        if (platform != 'mastodon' or parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path not in ('', '/') or any(c.isspace() for c in value)):
            raise ValueError
        parsed.port
    except ValueError:
        raise click.ClickException('Journal-Ziel muss eine Instanzadresse ohne Zugangsdaten sein.') from None
    return f'{parsed.scheme}://{parsed.netloc.lower()}'


def init_journal(conn: sqlite3.Connection) -> None:
    conn.execute('''CREATE TABLE IF NOT EXISTS publication_attempts (
        attempt_uuid TEXT PRIMARY KEY,
        platform TEXT NOT NULL,
        date_uuid TEXT NOT NULL,
        event_uuid TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('reserved','publishing','remote_succeeded','published','failed')),
        remote_id TEXT,
        remote_url TEXT,
        error_class TEXT,
        event_snapshot TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    # Additive migration of PR #32 databases; existing attempts retain unknown (NULL) context.
    columns = {row[1] for row in conn.execute('PRAGMA table_info(publication_attempts)')}
    for column in ('date_slug', 'mutation_stage', 'target_ref', 'content_sha256'):
        if column not in columns:
            conn.execute(f'ALTER TABLE publication_attempts ADD COLUMN {column} TEXT')
    conn.execute('''CREATE UNIQUE INDEX IF NOT EXISTS active_publication
        ON publication_attempts(platform, date_uuid)
        WHERE state IN ('reserved','publishing','remote_succeeded')''')


def list_attempts(conn: sqlite3.Connection, *, state: str | None = None, active: bool = False,
                  date_uuid: str | None = None, limit: int = 50) -> list[dict]:
    """Newest attempts first; filter/limit inside SQLite, never load the entire journal."""
    if state is not None and state not in STATES:
        raise click.ClickException('Unbekannter Veröffentlichungszustand.')
    if active and state and state not in ACTIVE:
        raise click.ClickException('--active kann nicht mit einem abgeschlossenen --state kombiniert werden.')
    if limit < 0:
        raise click.ClickException('--limit muss mindestens 0 sein.')
    conditions, values = [], []
    if state:
        conditions.append('state=?')
        values.append(state)
    if active:
        conditions.append("state IN ('reserved','publishing','remote_succeeded')")
    if date_uuid:
        conditions.append('date_uuid=?')
        values.append(date_uuid)
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    cursor = conn.execute('SELECT * FROM publication_attempts' + where
                          + ' ORDER BY created_at DESC, rowid DESC LIMIT ?', (*values, limit or -1))
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def get_attempt(conn: sqlite3.Connection, attempt_uuid: str) -> dict:
    cursor = conn.execute('SELECT * FROM publication_attempts WHERE attempt_uuid=?', (attempt_uuid,))
    row = cursor.fetchone()
    if row is None:
        raise click.ClickException('Veröffentlichungsversuch nicht gefunden.')
    return dict(zip([column[0] for column in cursor.description], row))


def unresolved_attempt(conn: sqlite3.Connection, date_uuid: str, platform: str | None = None) -> dict | None:
    cursor = conn.execute('''SELECT * FROM publication_attempts
        WHERE date_uuid=? AND (? IS NULL OR platform=?)
        AND state IN ('reserved','publishing','remote_succeeded') LIMIT 1''', (date_uuid, platform, platform))
    row = cursor.fetchone()
    return dict(zip([column[0] for column in cursor.description], row)) if row else None


def describe_attempt(attempt: dict) -> str:
    return (f"Plattform={attempt['platform']}, date_uuid={attempt['date_uuid']}, "
            f"Versuch={attempt['attempt_uuid']}, Status={attempt['state']}, "
            f"Remote-ID={attempt['remote_id'] or 'unbekannt'}, "
            f"Phase={attempt.get('mutation_stage') or 'unbekannt'}, "
            f"Fehlerklasse={attempt.get('error_class') or 'keine'}, "
            f"Ziel={attempt.get('target_ref') or 'unbekannt'}, "
            f"date_slug={attempt.get('date_slug') or 'unbekannt'}, "
            f"SHA256={attempt.get('content_sha256') or 'unbekannt'}")


def reserve_attempt(conn: sqlite3.Connection, platform: str, event: dict, *, allow_repeat: bool = False,
                    message: str = "", target_ref: str | None = None) -> str:
    attempt_uuid = str(uuid4())
    date_uuid = event['date']['uuid']
    target_ref = validate_target_ref(platform, target_ref)
    fingerprint = content_fingerprint(platform, event, message)
    # Recovery metadata and a content hash, never full social text or credentials.
    snapshot = {key: event[key] for key in ('uuid', 'title')}
    snapshot['date'] = {key: event['date'].get(key) for key in ('uuid', 'slug', 'start_date', 'start_time')}
    with transaction(conn):
        active = unresolved_attempt(conn, date_uuid, platform)
        if active:
            raise click.ClickException('Termin ist reserviert oder ungeklärt: ' + describe_attempt(active)
                                       + '. Mit kulturbytes-social attempts prüfen und auflösen.')
        if not allow_repeat and conn.execute('SELECT 1 FROM published_events WHERE date_uuid=?', (date_uuid,)).fetchone():
            raise click.ClickException('Termin wurde inzwischen veröffentlicht; keine erneute Veröffentlichung.')
        conn.execute('''INSERT INTO publication_attempts
            (attempt_uuid,platform,date_uuid,event_uuid,state,event_snapshot,date_slug,target_ref,content_sha256)
            VALUES (?,?,?,?,'reserved',?,?,?,?)''',
                     (attempt_uuid, platform, date_uuid, event['uuid'], json.dumps(snapshot, ensure_ascii=False),
                      event['date']['slug'], target_ref, fingerprint))
    return attempt_uuid


def _transition(conn: sqlite3.Connection, attempt_uuid: str, state: str, previous: tuple[str, ...],
                *, remote_id: str | None = None, remote_url: str | None = None,
                error_class: str | None = None, mutation_stage: str | None = None) -> None:
    """Pure SQL update: the caller owns the transaction."""
    placeholders = ','.join('?' for _ in previous)
    cursor = conn.execute(f'''UPDATE publication_attempts SET state=?,
        remote_id=COALESCE(?,remote_id), remote_url=COALESCE(?,remote_url),
        mutation_stage=COALESCE(?,mutation_stage), error_class=?, updated_at=CURRENT_TIMESTAMP
        WHERE attempt_uuid=? AND state IN ({placeholders})''',
        (state, remote_id, remote_url, mutation_stage, error_class, attempt_uuid, *previous))
    if cursor.rowcount != 1:
        raise click.ClickException('Veröffentlichungszustand wurde geändert; Vorgang abgebrochen.')


def begin_remote_mutation(stage: str) -> None:
    """Commit the specific stage before each content-creation POST."""
    if stage not in MUTATION_STAGES:
        raise click.ClickException('Unbekannte Veröffentlichungsphase.')
    current = _current.get()
    if current:
        conn, attempt_uuid = current
        with transaction(conn):
            if not stage.startswith(get_attempt(conn, attempt_uuid)['platform'] + '_'):
                raise click.ClickException('Veröffentlichungsphase passt nicht zur Plattform.')
            _transition(conn, attempt_uuid, 'publishing', ('reserved', 'publishing'), mutation_stage=stage)


def mark_remote_succeeded(conn: sqlite3.Connection, attempt_uuid: str, remote_id: str,
                          remote_url: str | None = None) -> None:
    if not isinstance(remote_id, str) or not remote_id:
        raise click.ClickException('Remote-Erfolg ohne gültige ID; manuelle Prüfung erforderlich.')
    with transaction(conn):
        _transition(conn, attempt_uuid, 'remote_succeeded', ('reserved', 'publishing'),
                    remote_id=remote_id, remote_url=remote_url)


def mark_published(conn: sqlite3.Connection, attempt_uuid: str) -> None:
    with transaction(conn):
        _transition(conn, attempt_uuid, 'published', ('remote_succeeded',))


def mark_failed(conn: sqlite3.Connection, attempt_uuid: str, error_class: str) -> None:
    with transaction(conn):
        _transition(conn, attempt_uuid, 'failed', ('reserved', 'publishing'), error_class=error_class)


def execute_publication(conn: sqlite3.Connection, platform: str, event: dict,
                        publish: Callable[[], tuple[str, str | None]],
                        finalize: Callable[[str, str | None], None], *, allow_repeat: bool = False,
                        message: str = "", target_ref: str | None = None) -> tuple[str, str | None]:
    attempt_uuid = reserve_attempt(conn, platform, event, allow_repeat=allow_repeat, message=message, target_ref=target_ref)
    token = _current.set((conn, attempt_uuid))
    remote_id = None
    try:
        remote_id, remote_url = publish()
        mark_remote_succeeded(conn, attempt_uuid, remote_id, remote_url)
        with transaction(conn):
            finalize(remote_id, remote_url)
            _transition(conn, attempt_uuid, 'published', ('remote_succeeded',))
        return remote_id, remote_url
    except Exception as exc:
        conn.rollback()
        if remote_id is not None:
            # Even a failure to persist the returned ID leaves the committed publishing reservation.
            raise click.ClickException(
                f'ACHTUNG: Remote-Veröffentlichung erfolgreich, lokale Speicherung unvollständig. '
                f'Plattform={platform}, date_uuid={event["date"]["uuid"]}, Versuch={attempt_uuid}, '
                f'Remote-ID={remote_id}. Nicht erneut posten; mit kulturbytes-social attempts prüfen.'
            ) from None
        attempt = get_attempt(conn, attempt_uuid)
        if attempt['state'] == 'reserved' or isinstance(exc, RemoteRejected):
            mark_failed(conn, attempt_uuid, type(exc).__name__)
            raise
        with transaction(conn):
            _transition(conn, attempt_uuid, 'publishing', ('publishing',), error_class=type(exc).__name__)
        attempt = get_attempt(conn, attempt_uuid)
        raise click.ClickException('Remote-Ergebnis ungeklärt; erneutes Posten gesperrt. '
                                   + describe_attempt(attempt) + '. Mit kulturbytes-social attempts prüfen.') from None
    finally:
        _current.reset(token)


def resolve_attempt(conn: sqlite3.Connection, attempt_uuid: str, outcome: str,
                    finalize: Callable[[dict, str, str | None], None], *, remote_id: str | None = None,
                    remote_url: str | None = None) -> None:
    """Operator has stopped the worker and checked the remote platform before calling."""
    with transaction(conn):
        attempt = get_attempt(conn, attempt_uuid)
        if attempt['state'] not in ACTIVE:
            raise click.ClickException('Versuch ist bereits abgeschlossen.')
        if outcome == 'failed':
            _transition(conn, attempt_uuid, 'failed', ('reserved', 'publishing'),
                        error_class='OperatorConfirmedNoPublication')
            return
        if outcome != 'published':
            raise click.ClickException('Unbekanntes Ergebnis.')
        if attempt['remote_id']:
            if remote_id and remote_id != attempt['remote_id']:
                raise click.ClickException('Remote-ID darf einen bestätigten Erfolg nicht überschreiben.')
            if remote_url and remote_url != attempt['remote_url']:
                raise click.ClickException('Remote-URL darf einen bestätigten Erfolg nicht überschreiben.')
            remote_id, remote_url = attempt['remote_id'], attempt['remote_url']
        else:
            # Recovery has no credentials to redact: accept actual numeric platform IDs only.
            pattern = r'[0-9]{1,100}(?:_[0-9]{1,100})?' if attempt['platform'] == 'facebook' else r'[0-9]{1,100}'
            if not remote_id or not re.fullmatch(pattern, remote_id):
                raise click.ClickException('Für Remote-Erfolg ist --remote-id mit einer gültigen numerischen Post-ID erforderlich.')
            if remote_url:
                from .auth import remote_url as safe_remote_url
                if not safe_remote_url(remote_url, ''):
                    raise click.ClickException('Remote-URL darf keine Zugangsdaten oder Query-Parameter enthalten.')
        if attempt['state'] != 'remote_succeeded':
            _transition(conn, attempt_uuid, 'remote_succeeded', ('reserved', 'publishing'),
                        remote_id=remote_id, remote_url=remote_url)
        finalize(json.loads(attempt['event_snapshot']), remote_id, remote_url)
        _transition(conn, attempt_uuid, 'published', ('remote_succeeded',))
