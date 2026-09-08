#!/usr/bin/env python3

import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlsplit

import click
import httpx

from kulturbytes_common.auth import check_auth_request, redact, response_payload
from kulturbytes_common.credentials import MASTODON, credential_options, resolve_credential
from kulturbytes_common.database import get_database_path
from kulturbytes_common.environment import get_config
from kulturbytes_common.events import (
    build_hashtags, format_price, get_event_url, get_start_datetime,
)
from kulturbytes_common.formatting import strip_markdown
from kulturbytes_common.media import download_image, get_image_url
from kulturbytes_common.workflow import run_publisher


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


DATABASE_PATH = get_database_path("mastodon")


def init_database() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS published_events (
            date_uuid TEXT PRIMARY KEY,
            event_uuid TEXT NOT NULL,
            mastodon_status_id TEXT NOT NULL,
            mastodon_status_url TEXT,
            title TEXT NOT NULL,
            start_date TEXT NOT NULL,
            start_time TEXT,
            published_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    return conn


def remember_post(
    conn: sqlite3.Connection,
    event: dict,
    mastodon_status_id: str,
    mastodon_status_url: str | None,
) -> None:
    event_date = event["date"]

    conn.execute(
        """
        INSERT INTO published_events (
            date_uuid,
            event_uuid,
            mastodon_status_id,
            mastodon_status_url,
            title,
            start_date,
            start_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date_uuid) DO UPDATE SET
            event_uuid = excluded.event_uuid,
            mastodon_status_id = excluded.mastodon_status_id,
            mastodon_status_url = excluded.mastodon_status_url,
            title = excluded.title,
            start_date = excluded.start_date,
            start_time = excluded.start_time,
            published_at = CURRENT_TIMESTAMP
        """,
        (
            event_date["uuid"],
            event["uuid"],
            mastodon_status_id,
            mastodon_status_url,
            event["title"],
            event_date["start_date"],
            event_date.get("start_time"),
        ),
    )

    conn.commit()


DEFAULT_STATUS_LIMIT = 500


def get_status_limit(client: httpx.Client, base_url: str) -> int:
    """Read public Mastodon v2 configuration; malformed/unavailable data uses 500."""
    try:
        response = client.get(f"{base_url}/api/v2/instance", follow_redirects=False)
        response.raise_for_status()
        value = response.json()
        for key in ("configuration", "statuses", "max_characters"):
            value = value.get(key) if isinstance(value, dict) else None
        if type(value) is int and value > 0:
            return value
    except (httpx.HTTPError, ValueError):
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


def print_event_preview(
    event: dict,
    message: str,
    max_length: int,
) -> None:
    click.echo()
    click.echo("=" * 80)

    click.echo(message)

    click.echo()
    click.echo(
        f"Zeichen: {len(message)}/{max_length}"
    )

    image_url = get_image_url(
        event
    )

    if image_url:
        click.echo()
        click.echo(
            f"🖼 {image_url}"
        )

        click.echo(
            "Alt-Text: "
            f"{get_image_alt_text(event)}"
        )

    click.echo("=" * 80)


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
        response = client.get(
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

    return str(media_id)


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

    response = client.post(
        f"{config.base_url}/api/v1/statuses",
        headers={
            "Authorization": f"Bearer {config.access_token}",
        },
        data=data,
    )

    payload = response_payload(response, "Mastodon", config.access_token)
    status_id = payload.get("id")

    if not status_id:
        raise RuntimeError(
            "Mastodon hat keine Status-ID zurückgegeben: "
            + redact(str(payload), config.access_token)
        )

    return str(status_id), payload.get("url")


def publish_event(
    client: httpx.Client,
    conn: sqlite3.Connection,
    event: dict,
    dry_run: bool,
    *,
    max_length: int = DEFAULT_STATUS_LIMIT,
    config: MastodonConfig | None = None,
) -> bool:
    message = build_mastodon_message(event, max_length=max_length)
    print_event_preview(event, message, max_length)

    if dry_run:
        click.secho(
            "DRY RUN: kein Mastodon-Post veröffentlicht.",
            fg="yellow",
        )

        return False

    if not click.confirm(
        "Diesen Termin jetzt auf Mastodon veröffentlichen?",
        default=False,
    ):
        click.echo(
            "Übersprungen."
        )

        return False

    (
        mastodon_status_id,
        mastodon_status_url,
    ) = publish_mastodon_status(
        client,
        event,
        message=message,
        config=config,
    )

    click.secho(
        (
            "Mastodon-Post erstellt: "
            f"{mastodon_status_id}"
        ),
        fg="green",
    )

    if mastodon_status_url:
        click.echo(
            mastodon_status_url
        )

    remember_post(
        conn,
        event,
        mastodon_status_id,
        mastodon_status_url,
    )

    click.echo(
        "Gespeichert: "
        f"{event['date']['uuid']} "
        f"-> {mastodon_status_id}"
    )

    return True


@click.command("mastodon", help="Kulturbytes-Termine für Mastodon auswählen, prüfen und veröffentlichen.")
@credential_options("Mastodon")
@click.option("--check-auth", "check_auth_only", is_flag=True, help="Nur Zugang und Zielkonto prüfen; hat Vorrang vor Auswahl und Veröffentlichung.")
@click.option(
    "--dry-run/--publish",
    default=True,
    help=(
        "Im Dry-Run-Modus nur Vorschau anzeigen. "
        "Mit --publish echte Mastodon-Posts erstellen."
    ),
)
@click.option(
    "--limit",
    type=click.IntRange(
        min=0,
    ),
    default=50,
    show_default=True,
    help=(
        "Maximale Anzahl Events in der Auswahl. "
        "0 zeigt alle."
    ),
)
@click.option(
    "--include-published",
    is_flag=True,
    help=(
        "Auch bereits veröffentlichte Events "
        "in der Auswahl anzeigen."
    ),
)
@click.option(
    "--city",
    type=str,
    default=None,
    help=(
        "Optional nach Stadt filtern, "
        "z.B. --city Flensburg."
    ),
)
@click.option(
    "--event-uuid",
    type=str,
    default=None,
    help="Event-UUID für die direkte Auswahl eines einzelnen Termins.",
)
@click.option(
    "--date-identifier",
    type=str,
    default=None,
    help="Termin-Slug oder Termin-UUID; benötigt --event-uuid.",
)
def mastodon_command(
    check_auth_only: bool,
    dry_run: bool,
    limit: int,
    include_published: bool,
    city: str | None,
    event_uuid: str | None,
    date_identifier: str | None,
) -> None:
    if check_auth_only:
        check_auth(load_config())
        return
    config = load_config() if not dry_run else None
    base_url = config.base_url if config else load_base_url()
    status_limit: int | None = None

    def publish_with_instance_limit(
        client: httpx.Client, conn: sqlite3.Connection, event: dict, dry_run: bool,
    ) -> bool:
        nonlocal status_limit
        if status_limit is None:
            status_limit = get_status_limit(client, base_url)
        return publish_event(client, conn, event, dry_run=dry_run, max_length=status_limit, config=config)

    run_publisher(
        conn=init_database(),
        publish_event=publish_with_instance_limit,
        user_agent="Kulturbytes-Mastodon-Publisher/1.0",
        dry_run=dry_run,
        limit=limit,
        include_published=include_published,
        city=city,
        event_uuid=event_uuid,
        date_identifier=date_identifier,
    )
