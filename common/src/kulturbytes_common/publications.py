"""Non-persistent publication metadata and mutation callbacks for adapters."""
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import re
from urllib.parse import urlsplit
import click

MUTATION_STAGES = frozenset({'facebook_photo', 'facebook_feed', 'mastodon_media', 'mastodon_status',
                             'instagram_container', 'instagram_publish'})
_current: ContextVar[Callable[[str], None] | None] = ContextVar('mutation_recorder', default=None)


@contextmanager
def mutation_recorder(callback: Callable[[str], None]) -> Iterator[None]:
    token = _current.set(callback)
    try:
        yield
    finally:
        _current.reset(token)


def begin_remote_mutation(stage: str) -> None:
    if stage not in MUTATION_STAGES:
        raise ValueError('Unknown mutation stage')
    callback = _current.get()
    if callback:
        callback(stage)


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
