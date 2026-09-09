"""Shared secret redaction and read-only authentication requests."""

import json
import re
from urllib.parse import quote, quote_plus, urlsplit

import click
import httpx

from kulturbytes_common.http import safe_get

from .publications import RemoteRejected


def redact(text: str, token: str) -> str:
    for secret in sorted(
        {
            token,
            quote(token, safe=""),
            quote_plus(token),
            json.dumps(token)[1:-1],
            json.dumps(token, ensure_ascii=False)[1:-1],
            repr(token)[1:-1],
        },
        key=len,
        reverse=True,
    ):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def response_payload(response: httpx.Response, platform: str, token: str) -> dict:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        raise api_error(response, payload, platform, token) from None
    if not isinstance(payload, dict) or payload.get("error"):
        raise api_error(response, payload, platform, token)
    return payload


def api_error(
    response: httpx.Response, payload: object, platform: str, token: str
) -> click.ClickException:
    message = f"{platform}-Zugriff konnte nicht validiert werden."
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and error.get("code") == 190:
        message = (
            f"{platform} Access Token ist abgelaufen."
            if error.get("error_subcode") == 463
            else f"{platform} Access Token ist ungültig oder abgelaufen."
        )
    elif platform == "Mastodon" and response.status_code in {401, 403}:
        message = "Mastodon-Zugangsdaten ungültig oder abgelaufen."
    definitive = response.status_code in {
        400,
        401,
        403,
        404,
        405,
        413,
        415,
        422,
        429,
    } or (200 <= response.status_code < 300 and bool(error))
    # A polling GET failure says nothing about the preceding mutation's outcome.
    error_type = (
        RemoteRejected
        if response.request.method == "POST" and definitive
        else click.ClickException
    )
    return error_type(
        f"{message} HTTP {response.status_code}: " + redact(response.text, token)
    )


def check_auth_request(
    platform: str, url: str, token: str, *, params: dict | None = None
) -> dict:
    # No redirects, event discovery, database access, or write requests.
    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0),
            follow_redirects=False,
            headers={
                "User-Agent": f"Kulturbytes-{platform}-Publisher/1.0",
                "Accept": "application/json",
            },
        ) as client:
            response = safe_get(
                client, url, params=params, headers={"Authorization": f"Bearer {token}"}
            )
            return response_payload(response, platform, token)
    except httpx.RequestError:
        # Transport exceptions can embed credentials or upstream URLs.
        raise click.ClickException(
            f"{platform}-Zugriff konnte nicht validiert werden: Netzwerkfehler."
        ) from None


def remote_identifier(value: object, platform: str, token: str) -> str:
    """Opaque remote IDs must be safe to persist, display and use as path segments."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (str, int))
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", str(value))
        or redact(str(value), token) != str(value)
    ):
        raise click.ClickException(
            f"{platform}: ungültige Remote-ID; Ergebnis manuell prüfen."
        )
    return str(value)


def remote_url(value: object, token: str) -> str | None:
    """Optional display metadata must never carry credentials into the journal."""
    if not isinstance(value, str) or redact(value, token) != value:
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or len(value) > 2000
            or any(c.isspace() or ord(c) < 32 for c in value)
        ):
            return None
        parsed.port
    except ValueError:
        return None
    return value
