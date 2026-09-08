"""Read-only Facebook Page token validation and recovery."""

import sys
from urllib.parse import urlsplit

import click
import httpx
from kulturbytes_common.http import safe_get

from kulturbytes_common.auth import redact
from kulturbytes_common.credentials import (
    FACEBOOK_PAGE, FACEBOOK_USER, optional_credential, set_secret, warn_legacy, meta_candidate, persist_validated_meta,
)


class InvalidPageToken(click.ClickException):
    """Only OAuth error 190 permits automatic recovery."""


def interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def request(client: httpx.Client, url: str, token: str, **params: str) -> dict:
    try:
        response = safe_get(client, url, params=params, headers={'Authorization': f'Bearer {token}'},
                              follow_redirects=False)
    except httpx.RequestError:
        raise click.ClickException('Facebook: Netzwerkfehler bei der Authentifizierung.') from None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    error = payload.get('error') if isinstance(payload, dict) else None
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        failed = True
    else:
        failed = False
    if failed or error or not isinstance(payload, dict):
        # Account-list bodies can contain tokens belonging to unrelated pages.
        # Never print raw bodies; retain only recognized numeric error metadata.
        code = error.get('code') if isinstance(error, dict) else None
        subcode = error.get('error_subcode') if isinstance(error, dict) else None
        message = f'Facebook: Zugriff fehlgeschlagen. HTTP {response.status_code} [REDACTED]'
        if type(code) is int:
            message += f' (Code {code})'
        if code == 190:
            message += ' Token ist abgelaufen.' if subcode == 463 else ' Token ist ungültig oder abgelaufen.'
            raise InvalidPageToken(message)
        raise click.ClickException(message)
    return payload


def validate(client: httpx.Client, base: str, page_id: str, token: str) -> str:
    payload = request(client, f'{base}/{page_id}', token, fields='id,name')
    if payload.get('id') != page_id:
        raise click.ClickException('Facebook: Zurückgegebene Seiten-ID stimmt nicht mit FACEBOOK_PAGE_ID überein.')
    name = payload.get('name')
    if not isinstance(name, str) or not name.strip():
        raise click.ClickException('Facebook: Die Antwort enthält keinen Seitennamen.')
    return name


def resolve_page_access_token(client: httpx.Client, *, user_access_token: str,
                              page_id: str, graph_api_version: str) -> str:
    url = f'https://graph.facebook.com/{graph_api_version}/me/accounts'
    params = {'fields': 'id,name,access_token'}
    seen: set[str] = set()
    for _ in range(1000):
        payload = request(client, url, user_access_token, **params)
        pages = payload.get('data')
        if not isinstance(pages, list):
            raise click.ClickException('Facebook: Ungültige Seitenliste (data).')
        matches = []
        for page in pages:
            if (not isinstance(page, dict) or not isinstance(page.get('id'), str)
                    or not page['id'].isascii() or not page['id'].isdigit()
                    or not isinstance(page.get('name'), str) or not page['name'].strip()):
                raise click.ClickException('Facebook: Ungültiger Eintrag in der Seitenliste.')
            if page['id'] == page_id:
                token = page.get('access_token')
                if not isinstance(token, str) or not token.strip():
                    raise click.ClickException('Facebook: Für die konfigurierte Seite fehlt der Page Access Token.')
                matches.append(token.strip())
        paging = payload.get('paging', {})
        if not isinstance(paging, dict):
            raise click.ClickException('Facebook: Ungültige Pagination.')
        next_url = paging.get('next')
        if next_url is not None:
            if not isinstance(next_url, str):
                raise click.ClickException('Facebook: Ungültige Pagination.')
            try:
                parsed = urlsplit(next_url)
                safe = (parsed.scheme == 'https' and parsed.netloc == 'graph.facebook.com'
                        and parsed.path == f'/{graph_api_version}/me/accounts' and not parsed.fragment)
            except ValueError:
                safe = False
            cursors = paging.get('cursors')
            after = cursors.get('after') if isinstance(cursors, dict) else None
            if not safe or not isinstance(after, str) or not after or after in seen:
                raise click.ClickException('Facebook: Ungültige oder zyklische Pagination.')
            seen.add(after)
            # Reconstruct the URL: never follow next URLs or their access_token query.
            params['after'] = after
        if len(matches) > 1:
            raise click.ClickException('Facebook: Konfigurierte Seite ist nicht eindeutig.')
        if matches:
            return matches[0]
        if next_url is None:
            raise click.ClickException('Facebook: FACEBOOK_PAGE_ID wurde in /me/accounts nicht gefunden.')
    raise click.ClickException('Facebook: Zu viele Seiten der Pagination.')


def authenticate_legacy_page(page_id: str, version: str, *, force: bool = False, secrets: list[str] | None = None, allow_prompt: bool = True) -> str:
    warn_legacy('Facebook')
    page_token = None if force else optional_credential(FACEBOOK_PAGE)
    secrets = secrets if secrets is not None else []
    if page_token:
        secrets.append(page_token)
    original_error = None
    with httpx.Client(
        timeout=httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0),
        follow_redirects=False,
        headers={'User-Agent': 'Kulturbytes-Facebook-Publisher/1.0', 'Accept': 'application/json'},
    ) as client:
        if page_token:
            try:
                name = validate(client, f'https://graph.facebook.com/{version}', page_id, page_token)
            except InvalidPageToken as exc:
                original_error = exc
                click.echo('Facebook Page Access Token ist ungültig oder abgelaufen.')
            else:
                click.echo('✓ Facebook Token gültig')
                click.echo(redact(f'✓ Seite erreichbar: {name} ({page_id})', page_token))
                return page_token
        tty = allow_prompt and interactive()
        if tty and not force and not click.confirm('Mit einem User Access Token wiederherstellen?', default=False):
            raise click.ClickException('Facebook: Wiederherstellung abgebrochen.')
        user_token = optional_credential(FACEBOOK_USER)
        if not user_token and tty:
            user_token = click.prompt('Facebook User Access Token', hide_input=True).strip()
        if not user_token:
            suffix = ' FACEBOOK_USER_ACCESS_TOKEN fehlt in Environment/OS-Keyring; interaktive Eingabe erfordert ein TTY.'
            raise click.ClickException((original_error.message if original_error else 'Facebook Page Access Token fehlt.') + suffix)
        secrets.append(user_token)
        click.echo('Versuche Wiederherstellung über User Access Token ...')
        token = resolve_page_access_token(client, user_access_token=user_token,
                                         page_id=page_id, graph_api_version=version)
        secrets.append(token)
        name = validate(client, f'https://graph.facebook.com/{version}', page_id, token)
        output = f'✓ Seite erreichbar: {name} ({page_id})'
        for secret in secrets:
            output = redact(output, secret)
        click.echo(output)
        click.echo('✓ Neuer Page Access Token validiert')
        if tty and click.confirm('Page Access Token im OS-Keyring speichern?', default=True):
            set_secret(FACEBOOK_PAGE.service, FACEBOOK_PAGE.username, token)
            click.echo('✓ Page Access Token im OS-Keyring gespeichert.')
        return token


def authenticate_page(page_id: str, version: str, *, force: bool = False,
                      secrets: list[str] | None = None, allow_prompt: bool = True) -> str:
    candidate = meta_candidate((FACEBOOK_PAGE, FACEBOOK_USER), allow_prompt=allow_prompt)
    if candidate is None:
        return authenticate_legacy_page(page_id, version, force=force, secrets=secrets, allow_prompt=allow_prompt)
    system_token = candidate.value
    secrets = secrets if secrets is not None else []
    secrets.append(system_token)
    with httpx.Client(
        timeout=httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0),
        follow_redirects=False,
        headers={'User-Agent': 'Kulturbytes-Facebook-Publisher/1.0', 'Accept': 'application/json'},
    ) as client:
        token = resolve_page_access_token(client, user_access_token=system_token,
                                         page_id=page_id, graph_api_version=version)
        secrets.append(token)
        name = validate(client, f'https://graph.facebook.com/{version}', page_id, token)
    persist_validated_meta(candidate)
    output = f'✓ Facebook-Seite erreichbar: {name} ({page_id})'
    for secret in secrets:
        output = redact(output, secret)
    click.echo(output)
    click.echo('✓ Facebook Publishing-Ziel mit Meta System User Token validiert')
    return token
