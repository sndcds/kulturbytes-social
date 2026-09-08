#!/usr/bin/env python3

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import click
import httpx
from kulturbytes_common.auth import remote_identifier, remote_url
from kulturbytes_common.publications import begin_remote_mutation
from kulturbytes_common.http import safe_get

from kulturbytes_common.auth import check_auth_request, redact, response_payload
from kulturbytes_common.credentials import MASTODON, resolve_credential
from kulturbytes_common.environment import get_config
from kulturbytes_common.events import (
    build_hashtags, format_price, get_event_url, get_start_datetime,
)
from kulturbytes_common.formatting import strip_markdown
from kulturbytes_common.media import download_image, get_image_url


@dataclass(frozen=True)
class MastodonConfig:
    base_url: str
    access_token: str = field(repr=False)


def load_base_url() -> str:
    base_url = get_config("MASTODON_BASE_URL", "https://norden.social").strip().rstrip("/")
    try:
        parsed = urlsplit(base_url)
        valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                 and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment and not parsed.path
                 and not any(character.isspace() for character in base_url))
        parsed.port  # Reject malformed port numbers too.
    except ValueError:
        valid = False
    if not valid:
        raise click.ClickException("MASTODON_BASE_URL muss eine HTTP(S)-Instanzadresse ohne Zugangsdaten, Pfad oder Query sein.")
    return base_url


def load_config() -> MastodonConfig:
    token = resolve_credential(MASTODON)
    if not token:
        raise click.ClickException("MASTODON_ACCESS_TOKEN fehlt.")
    return MastodonConfig(load_base_url(), token)


def check_auth(config: MastodonConfig) -> None:
    payload = check_auth_request(
        "Mastodon", f"{config.base_url}/api/v1/accounts/verify_credentials", config.access_token,
    )
    acct = payload.get("acct") or payload.get("username")
    if not payload.get("id") or not isinstance(acct, str) or not acct.strip():
        raise click.ClickException("Mastodon: Die Antwort enthält kein gültiges Konto.")
    if "@" not in acct:
        acct = f"{acct}@{urlsplit(config.base_url).netloc}"
    click.echo("✓ Mastodon Token gültig")
    click.echo(redact(f"✓ Konto: @{acct}", config.access_token))








DEFAULT_STATUS_LIMIT = 500


def get_status_limit(client: httpx.Client, base_url: str) -> int:
    """Read public Mastodon v2 configuration; malformed/unavailable data uses 500."""
    try:
        response = safe_get(client, f"{base_url}/api/v2/instance", follow_redirects=False)
        response.raise_for_status()
        value = response.json()
        for key in ("configuration", "statuses", "max_characters"):
            value = value.get(key) if isinstance(value, dict) else None
        if type(value) is int and value > 0:
            return value
    except (httpx.HTTPError, ValueError, click.ClickException):
        pass
    click.echo("Mastodon-Instanzlimit nicht verfügbar; verwende 500 Zeichen.", err=True)
    return DEFAULT_STATUS_LIMIT


def trim_summary(summary: str, available: int) -> str:
    """Keep complete whitespace-delimited words; never slice a word or URL."""
    if len(summary) <= available:
        return summary
    end = 0
    for word in re.finditer(r"\S+", summary):
        if word.end() + 1 > available:
            break
        end = word.end()
    return summary[:end] + "…" if end else ""


def build_mastodon_message(event: dict, max_length: int = DEFAULT_STATUS_LIMIT) -> str:
    event_date = event["date"]
    start = get_start_datetime(event)
    header = [f"📅 {strip_markdown(event.get('title') or '')}"]
    date_line = f"🗓 {start:%d.%m.%Y} · {start:%H:%M} Uhr"
    end_date = event_date.get("end_date")
    if end_date and end_date != event_date["start_date"]:
        date_line += f" – {date.fromisoformat(end_date):%d.%m.%Y}"
    header.append(date_line)
    venue = strip_markdown(event_date.get("venue_name") or "")
    city = strip_markdown(event_date.get("venue_city") or "")
    location = [venue] if venue else []
    if city and city.casefold() != venue.casefold():
        location.append(city)
    if location:
        header.append("📍 " + ", ".join(location))
    footer = [f"👉 {get_event_url(event)}", build_hashtags(event)]

    def compose() -> str:
        return "\n".join(header) + "\n\n" + "\n".join(footer)

    if len(compose()) > max_length:
        raise click.ClickException(
            "Mastodon-Text ist bereits ohne Beschreibung länger als das "
            f"Instanzlimit von {max_length} Zeichen. Veröffentlichung wurde abgebrochen."
        )

    # Keep all required metadata and hashtags. Optional priority: subtitle,
    # price, ticket URL, organizer, then summary. Drop metadata only as a whole.
    subtitle = strip_markdown(event.get("subtitle") or "")
    price = format_price(event)
    ticket = event_date.get("ticket_link")
    organizer = strip_markdown(event.get("org_name") or "")
    for value, target in [(subtitle, header), (price, footer),
                          (f"🎟 {ticket}" if ticket else "", footer),
                          (f"Veranstalter: {organizer}" if organizer else "", footer)]:
        if value and len(compose()) + len(value) + 1 <= max_length:
            # Subtitle follows title; optional footer metadata precedes the link.
            index = 1 if target is header else len(footer) - 2
            target.insert(index, value)

    summary = strip_markdown(event.get("summary") or event.get("description") or "")
    summary = trim_summary(summary, max_length - len(compose()) - 2)
    if summary:
        return "\n".join(header) + "\n\n" + summary + "\n\n" + "\n".join(footer)
    return compose()


def get_image_alt_text(
    event: dict,
) -> str:
    main_image = (
        event.get("images", {})
        .get("main", {})
    )

    alt = main_image.get("alt")

    if alt:
        return alt.strip()

    return (
        f"Veranstaltungsbild zu "
        f"{event['title']}"
    )




def wait_for_media(
    client: httpx.Client,
    media_id: str,
    *, config: MastodonConfig | None = None,
) -> None:
    config = config or load_config()
    url = (
        f"{config.base_url}"
        f"/api/v1/media/{media_id}"
    )

    for _ in range(10):
        response = safe_get(client,
            url,
            headers={
                "Authorization": (
                    f"Bearer "
                    f"{config.access_token}"
                ),
            },
        )

        if response.status_code == 200:
            payload = response.json()

            if payload.get("url"):
                return

        time.sleep(1)

    click.secho(
        (
            "WARNUNG: Media-Verarbeitung "
            "ist möglicherweise noch nicht abgeschlossen."
        ),
        fg="yellow",
    )


def upload_mastodon_media(
    client: httpx.Client,
    event: dict,
    *, config: MastodonConfig | None = None,
) -> str:
    config = config or load_config()
    (
        image_bytes,
        content_type,
        filename,
    ) = download_image(
        client,
        event,
    )

    url = (
        f"{config.base_url}"
        "/api/v2/media"
    )

    begin_remote_mutation("mastodon_media")
    response = client.post(
        url,
        headers={
            "Authorization": (
                f"Bearer "
                f"{config.access_token}"
            ),
        },
        data={
            "description": (
                get_image_alt_text(event)
            ),
        },
        follow_redirects=False,
        files={
            "file": (
                filename,
                image_bytes,
                content_type,
            ),
        },
    )

    payload = response_payload(response, "Mastodon", config.access_token)

    media_id = payload.get("id")

    if not media_id:
        raise RuntimeError(
            "Mastodon hat keine "
            "Media-ID zurückgegeben: "
            + redact(str(payload), config.access_token)
        )

    return remote_identifier(media_id, "Mastodon", config.access_token)


def publish_mastodon_status(
    client: httpx.Client,
    event: dict,
    *,
    message: str | None = None,
    config: MastodonConfig | None = None,
) -> tuple[str, str | None]:
    config = config or load_config()
    if message is None:
        message = build_mastodon_message(event)
    media_id = None

    if get_image_url(event):
        media_id = upload_mastodon_media(client, event, config=config)
        wait_for_media(client, media_id, config=config)

    data = {
        "status": message,
        "visibility": "public",
    }

    if media_id:
        data["media_ids[]"] = media_id

    begin_remote_mutation("mastodon_status")
    response = client.post(
        f"{config.base_url}/api/v1/statuses",
        headers={
            "Authorization": f"Bearer {config.access_token}",
        },
        data=data,
        follow_redirects=False,
    )

    payload = response_payload(response, "Mastodon", config.access_token)
    status_id = payload.get("id")

    if not status_id:
        raise RuntimeError(
            "Mastodon hat keine Status-ID zurückgegeben: "
            + redact(str(payload), config.access_token)
        )

    return (remote_identifier(status_id, "Mastodon", config.access_token),
            remote_url(payload.get("url"), config.access_token))
