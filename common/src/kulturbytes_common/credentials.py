"""Optional OS credential storage; environment overrides never access the keyring."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

import click
import keyring


@dataclass(frozen=True)
class Credential:
    env_name: str
    service: str
    username: str
    label: str


META_SYSTEM_USER = Credential('META_SYSTEM_USER_ACCESS_TOKEN', 'kulturbytes-social/meta',
                              'system-user-access-token', 'Meta System User Access Token')
FACEBOOK_PAGE = Credential('FACEBOOK_PAGE_ACCESS_TOKEN', 'kulturbytes-social/facebook', 'page-access-token', 'Page Access Token')
FACEBOOK_USER = Credential('FACEBOOK_USER_ACCESS_TOKEN', 'kulturbytes-social/facebook', 'user-access-token', 'User Access Token')
INSTAGRAM = Credential('INSTAGRAM_ACCESS_TOKEN', 'kulturbytes-social/instagram', 'access-token', 'Access Token')
MASTODON = Credential('MASTODON_ACCESS_TOKEN', 'kulturbytes-social/mastodon', 'access-token', 'Access Token')
PLATFORMS = {'Facebook': {'meta': META_SYSTEM_USER, 'page': FACEBOOK_PAGE, 'user': FACEBOOK_USER},
             'Instagram': {'meta': META_SYSTEM_USER, 'access': INSTAGRAM}, 'Mastodon': {'access': MASTODON}}
KEYRING_ERROR = ('OS-Keyring ist nicht verfügbar. Verwende eine Environment-Variable '
                 'oder eine unterstützte Secret-Service-Sitzung bzw. einen OS-Schlüsselbund.')


def _require_os_backend() -> None:
    """Exclude plaintext/file plugins and disabled backends before reading or writing."""
    def supported(backend: object) -> bool:
        module = type(backend).__module__
        if module == 'keyring.backends.chainer':
            children = backend.backends
            return bool(children) and all(supported(child) for child in children)
        return module in {'keyring.backends.SecretService', 'keyring.backends.kwallet',
                          'keyring.backends.macOS', 'keyring.backends.Windows'}

    if not supported(keyring.get_keyring()):
        raise RuntimeError('Unsupported OS backend')


def get_secret(service: str, username: str) -> str | None:
    try:
        _require_os_backend()
        return keyring.get_password(service, username)
    except Exception:
        # Backend initialization and D-Bus errors can contain secrets.
        raise click.ClickException(KEYRING_ERROR) from None


def set_secret(service: str, username: str, value: str) -> None:
    try:
        _require_os_backend()
        keyring.set_password(service, username, value)
    except Exception:
        raise click.ClickException(KEYRING_ERROR) from None


def delete_secret(service: str, username: str) -> bool:
    if get_secret(service, username) is None:
        return False
    try:
        keyring.delete_password(service, username)
        return True
    except keyring.errors.PasswordDeleteError:
        # Only suppress a missing entry; permission failures are still errors.
        if get_secret(service, username) is None:
            return False
        raise click.ClickException(KEYRING_ERROR) from None
    except Exception:
        raise click.ClickException(KEYRING_ERROR) from None


def resolve_secret(*, env_name: str, service: str, username: str) -> str | None:
    if env_name in os.environ:
        # Even an explicitly empty override suppresses keyring access.
        return os.environ[env_name].strip() or None
    value = get_secret(service, username)
    return (value.strip() or None) if value is not None else None


def resolve_credential(credential: Credential) -> str | None:
    return resolve_secret(env_name=credential.env_name, service=credential.service, username=credential.username)


def optional_credential(credential: Credential) -> str | None:
    """Allow legacy env credentials when the optional shared keyring is unavailable."""
    try:
        return resolve_credential(credential)
    except click.ClickException:
        return None


def warn_legacy(platform: str) -> None:
    click.echo(f'{platform}: Legacy-Zugang ist veraltet; bitte auf META_SYSTEM_USER_ACCESS_TOKEN migrieren.', err=True)


def manage_credentials(platform: str, action: str, selected: str | None) -> None:
    choices = PLATFORMS[platform]
    selected = selected or ('meta' if 'meta' in choices else next(iter(choices)))
    if 'meta' in choices and selected != 'meta':
        warn_legacy(platform)
    credential = choices[selected]
    if action == 'status':
        click.echo(platform)
        present = resolve_credential(credential) is not None
        click.echo(f"{'✓' if present else '✗'} {credential.label} "
                   f"{'vorhanden' if present else 'nicht vorhanden'}")
        return
    if action == 'set':
        value = click.prompt(f'{platform} {credential.label}', hide_input=True).strip()
        if not value:
            raise click.ClickException('Token darf nicht leer sein.')
        set_secret(credential.service, credential.username, value)
        click.echo('✓ Token im OS-Keyring gespeichert.')
    elif click.confirm(f'{platform} {credential.label} aus dem OS-Keyring löschen?', default=False):
        deleted = delete_secret(credential.service, credential.username)
        click.echo('✓ Credential gelöscht.' if deleted else 'Credential im OS-Keyring nicht vorhanden.')


def credential_options(platform: str) -> Callable:
    """Add explicit management options without changing the existing Click command model."""
    def decorate(callback: Callable) -> Callable:
        @click.option('--credentials', type=click.Choice(['status', 'set', 'delete']),
                      help='Token-Präsenz prüfen, Token verdeckt speichern oder nach Bestätigung löschen.')
        @click.option('--credential', type=click.Choice(list(PLATFORMS[platform])),
                      help='Token für --credentials auswählen; kein Tokenwert.')
        @wraps(callback)
        def wrapped(*args: Any, credentials: str | None, credential: str | None, **kwargs: Any) -> Any:
            if credentials is not None:
                if kwargs.get('check_auth_only') or kwargs.get('resolve_page_token') or kwargs.get('dry_run') is False:
                    raise click.UsageError('--credentials kann nicht mit --publish, --check-auth oder --resolve-page-token kombiniert werden.')
                return manage_credentials(platform, credentials, credential)
            if credential is not None:
                raise click.UsageError('--credential benötigt --credentials.')
            return callback(*args, **kwargs)
        return wrapped
    return decorate
