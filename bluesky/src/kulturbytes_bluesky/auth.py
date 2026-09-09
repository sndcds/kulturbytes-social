"""App Password authentication against an explicitly configured HTTPS PDS."""

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import click
import httpx

from kulturbytes_common.atproto_identity import valid_did
from kulturbytes_common.auth import redact
from kulturbytes_common.credentials import BLUESKY, resolve_credential
from kulturbytes_common.environment import get_config
from kulturbytes_common.publications import RemoteRejected


@dataclass(frozen=True)
class BlueskyConfig:
    service_url: str
    handle: str
    app_password: str = field(repr=False)


@dataclass(frozen=True)
class Session:
    service_url: str
    did: str
    handle: str
    access_jwt: str = field(repr=False)
    secrets: tuple[str, ...] = field(default=(), repr=False)


def valid_handle(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 253
        and bool(
            re.fullmatch(
                r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?",
                value,
            )
        )
    )


def load_service_url() -> str:
    value = get_config("BLUESKY_SERVICE_URL", "https://bsky.social").strip().rstrip("/")
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or any(c.isspace() or ord(c) < 32 for c in value)
        ):
            raise ValueError
        parsed.port
        return str(httpx.URL(value)).rstrip("/")
    except (ValueError, httpx.InvalidURL):
        raise click.ClickException(
            "BLUESKY_SERVICE_URL benötigt eine HTTPS-PDS-Adresse ohne Zugangsdaten, Pfad oder Query."
        ) from None


def load_config() -> BlueskyConfig:
    service = load_service_url()
    handle = get_config("BLUESKY_HANDLE", "").strip()
    if not valid_handle(handle):
        raise click.ClickException("BLUESKY_HANDLE fehlt oder ist ungültig.")
    password = resolve_credential(BLUESKY)
    if not password:
        raise click.ClickException(
            "BLUESKY_APP_PASSWORD fehlt; ein Bluesky App Password verwenden."
        )
    return BlueskyConfig(service, handle.lower(), password)


def xrpc(
    client: httpx.Client,
    service: str,
    method: str,
    *,
    token: str | None = None,
    **kwargs,
) -> dict:
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = client.post(
            f"{service}/xrpc/{method}",
            headers=headers,
            follow_redirects=False,
            **kwargs,
        )
    except (httpx.RequestError, httpx.InvalidURL):
        raise click.ClickException(
            "Bluesky: Netzwerkfehler; Ergebnis der Anfrage ungeklärt."
        ) from None
    # Never echo API bodies: they can contain passwords and newly issued JWTs,
    # including unknown refresh tokens that a single-secret redactor cannot cover.
    if not 200 <= response.status_code < 300:
        error = (
            RemoteRejected
            if 400 <= response.status_code < 500 and response.status_code != 408
            else click.ClickException
        )
        raise error(
            f"Bluesky: XRPC-Anfrage fehlgeschlagen (HTTP {response.status_code})."
        )
    try:
        payload = response.json()
    except ValueError:
        raise click.ClickException(
            "Bluesky: ungültige JSON-Antwort; Ergebnis manuell prüfen."
        ) from None
    if not isinstance(payload, dict) or payload.get("error"):
        raise click.ClickException(
            "Bluesky: ungültige XRPC-Antwort; Ergebnis manuell prüfen."
        )
    return payload


def authenticate(client: httpx.Client, config: BlueskyConfig) -> Session:
    payload = xrpc(
        client,
        config.service_url,
        "com.atproto.server.createSession",
        json={"identifier": config.handle, "password": config.app_password},
    )
    did, handle, jwt = (
        payload.get("did"),
        payload.get("handle"),
        payload.get("accessJwt"),
    )
    secrets = (config.app_password, jwt, payload.get("refreshJwt"))
    if (
        not valid_did(did)
        or not valid_handle(handle)
        or handle.lower() != config.handle.lower()
        or not isinstance(jwt, str)
        or len(jwt) > 16384
        or not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", jwt)
        or any(
            isinstance(secret, str)
            and secret
            and (redact(did, secret) != did or redact(handle, secret) != handle)
            for secret in secrets
        )
    ):
        raise click.ClickException(
            "Bluesky: Session enthält keine gültige Kontoidentität oder Zugangsdaten."
        )
    return Session(
        config.service_url,
        did,
        handle.lower(),
        jwt,
        tuple(secret for secret in secrets if isinstance(secret, str) and secret),
    )
