"""Shared secret redaction and read-only authentication requests."""

import json
from urllib.parse import quote, quote_plus

import click
import httpx
from kulturbytes_common.http import safe_get


def redact(text: str, token: str) -> str:
    for secret in sorted({token, quote(token, safe=""), quote_plus(token),
                          json.dumps(token)[1:-1], json.dumps(token, ensure_ascii=False)[1:-1], repr(token)[1:-1]},
                         key=len, reverse=True):
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


def api_error(response: httpx.Response, payload: object, platform: str, token: str) -> click.ClickException:
    message = f"{platform}-Zugriff konnte nicht validiert werden."
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and error.get("code") == 190:
        message = (f"{platform} Access Token ist abgelaufen." if error.get("error_subcode") == 463
                   else f"{platform} Access Token ist ungültig oder abgelaufen.")
    elif platform == "Mastodon" and response.status_code in {401, 403}:
        message = "Mastodon-Zugangsdaten ungültig oder abgelaufen."
    return click.ClickException(
        f"{message} HTTP {response.status_code}: " + redact(response.text, token)
    )


def check_auth_request(platform: str, url: str, token: str, *, params: dict | None = None) -> dict:
    # No redirects, retries, event discovery, database access, or write requests.
    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0),
            follow_redirects=False,
            headers={"User-Agent": f"Kulturbytes-{platform}-Publisher/1.0", "Accept": "application/json"},
        ) as client:
            response = safe_get(client, url, params=params, headers={"Authorization": f"Bearer {token}"})
            return response_payload(response, platform, token)
    except httpx.RequestError:
        # Transport exceptions can embed credentials or upstream URLs.
        raise click.ClickException(f"{platform}-Zugriff konnte nicht validiert werden: Netzwerkfehler.") from None
