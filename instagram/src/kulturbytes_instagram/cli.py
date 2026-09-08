"""Publish Kulturbytes event photos through the Instagram Content Publishing API."""

import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlsplit

import click
import httpx
from kulturbytes_common.http import safe_get

from kulturbytes_common.auth import check_auth_request, redact, response_payload
from kulturbytes_common.credentials import (
    INSTAGRAM, credential_options, resolve_credential, warn_legacy, meta_candidate, persist_validated_meta,
)
from kulturbytes_common.database import get_database_path, open_database
from kulturbytes_common.environment import ResolvedValue, get_config
from kulturbytes_common.events import (
    build_address, build_hashtags, format_price, get_event_url, get_start_datetime,
)
from kulturbytes_common.formatting import strip_markdown
from kulturbytes_common.media import get_image_url
from kulturbytes_common.media_security import media_response
from kulturbytes_common.workflow import run_publisher

CAPTION_LIMIT = 2200
HASHTAG_LIMIT = 5  # Conservative application cap, including Kulturbytes and city.
POLL_ATTEMPTS = 5
POLL_INTERVAL = 60
DATABASE_PATH = None  # Optional in-process override; resolve configuration lazily.


@dataclass(frozen=True)
class InstagramConfig:
    user_id: str
    access_token: str = field(repr=False)
    base_url: str
    primary: ResolvedValue | None = field(default=None, repr=False)


def load_config(*, allow_prompt: bool = False) -> InstagramConfig:
    """Credentials are needed for publishing and auth checks; dry run works without them."""
    user_id = get_config("INSTAGRAM_USER_ID", "").strip()
    if not user_id:
        raise click.ClickException("INSTAGRAM_USER_ID fehlt.")
    candidate = meta_candidate((INSTAGRAM,), allow_prompt=allow_prompt)
    system_token = candidate.value if candidate else None
    token = system_token or resolve_credential(INSTAGRAM)
    login = get_config("INSTAGRAM_LOGIN_TYPE", "facebook" if system_token else "instagram").strip().lower()
    if system_token and login == "instagram":
        raise click.ClickException("META_SYSTEM_USER_ACCESS_TOKEN benötigt INSTAGRAM_LOGIN_TYPE=facebook; Instagram Login ist nur mit Legacy-Token möglich.")
    if not system_token and token:
        warn_legacy("Instagram")
    version = get_config("INSTAGRAM_GRAPH_API_VERSION", "v26.0").strip()
    if not user_id or not token:
        raise click.ClickException("INSTAGRAM_USER_ID und/oder Meta-Zugang fehlen (META_SYSTEM_USER_ACCESS_TOKEN; Legacy: INSTAGRAM_ACCESS_TOKEN).")
    if not user_id.isascii() or not user_id.isdigit():
        raise click.ClickException("INSTAGRAM_USER_ID muss die numerische Instagram-Konto-ID sein.")
    hosts = {"instagram": "graph.instagram.com", "facebook": "graph.facebook.com"}
    if login not in hosts:
        raise click.ClickException("INSTAGRAM_LOGIN_TYPE muss instagram oder facebook sein.")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+", version):
        raise click.ClickException("INSTAGRAM_GRAPH_API_VERSION muss z.B. v26.0 sein.")
    return InstagramConfig(user_id, token, f"https://{hosts[login]}/{version}", candidate)


def init_database() -> sqlite3.Connection:
    conn = open_database(DATABASE_PATH or get_database_path("instagram"), "instagram")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS published_events (
            date_uuid TEXT PRIMARY KEY,
            event_uuid TEXT NOT NULL,
            instagram_media_id TEXT NOT NULL,
            title TEXT NOT NULL,
            start_date TEXT NOT NULL,
            start_time TEXT,
            published_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def remember_post(conn: sqlite3.Connection, event: dict, media_id: str) -> None:
    event_date = event["date"]
    # An explicitly confirmed repeat publication replaces the stored remote ID.
    conn.execute("""
        INSERT INTO published_events
            (date_uuid, event_uuid, instagram_media_id, title, start_date, start_time)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(date_uuid) DO UPDATE SET
            event_uuid=excluded.event_uuid,
            instagram_media_id=excluded.instagram_media_id,
            title=excluded.title, start_date=excluded.start_date,
            start_time=excluded.start_time, published_at=CURRENT_TIMESTAMP
    """, (event_date["uuid"], event["uuid"], media_id, event["title"],
          event_date["start_date"], event_date.get("start_time")))
    conn.commit()


def build_instagram_caption(event: dict) -> str:
    event_date = event["date"]
    start = get_start_datetime(event)
    header = [f"📅 {strip_markdown(event.get('title') or '')}"]
    subtitle = strip_markdown(event.get("subtitle") or "")
    if subtitle:
        header.append(subtitle)
    header.append(f"🗓 {start:%d.%m.%Y} · {start:%H:%M} Uhr")
    end_date = event_date.get("end_date")
    if end_date and end_date != event_date["start_date"]:
        header.append(f"bis {date.fromisoformat(end_date):%d.%m.%Y}")
    location = strip_markdown(event_date.get("venue_name") or "")
    address = strip_markdown(build_address(event))
    if location:
        header.append(f"📍 {location}")
    if address:
        header.append(address)
    price = format_price(event)
    if price:
        header.append(price)
    organization = strip_markdown(event.get("org_name") or "")
    if organization:
        header.append(f"Veranstalter: {organization}")
    if event_date.get("ticket_link"):
        header.append(f"🎟 {event_date['ticket_link']}")

    # Prioritize required hashtags, then fill remaining slots with event tags.
    required = build_hashtags({"date": event_date}).split()
    tags = list(required)
    seen = {tag.casefold() for tag in tags}
    for tag in build_hashtags(event).split():
        if tag.casefold() not in seen and len(tags) < HASHTAG_LIMIT:
            tags.append(tag)
            seen.add(tag.casefold())
    footer = f"👉 {get_event_url(event)}\n{' '.join(tags)}"
    header_text = "\n".join(header)
    fixed = f"{header_text}\n\n{footer}"
    if len(fixed) > CAPTION_LIMIT:
        raise ValueError("Instagram: Titel/Metadaten sind zu lang; Link und Hashtags werden nicht abgeschnitten.")
    summary = strip_markdown(event.get("summary") or event.get("description") or "")
    available = CAPTION_LIMIT - len(fixed) - 2
    if summary and available > 1:
        if len(summary) > available:
            summary = summary[:available - 1].rstrip() + "…"
        return f"{header_text}\n\n{summary}\n\n{footer}"
    return fixed


def check_auth(config: InstagramConfig) -> None:
    payload = check_auth_request(
        "Instagram", f"{config.base_url}/{config.user_id}", config.access_token,
        params={"fields": "id,username"},
    )
    if str(payload.get("id")) != config.user_id:
        raise click.ClickException("Instagram: Zurückgegebene Konto-ID stimmt nicht mit INSTAGRAM_USER_ID überein.")
    username = payload.get("username")
    if not isinstance(username, str) or not username.strip():
        raise click.ClickException("Instagram: Die Antwort enthält keinen Benutzernamen.")
    login = "facebook" if urlsplit(config.base_url).hostname == "graph.facebook.com" else "instagram"
    click.echo("✓ Instagram Token gültig")
    click.echo(redact(f"✓ Konto: @{username}", config.access_token))
    click.echo(f"✓ Login-Typ: {login}")


def instagram_request(
    client: httpx.Client, config: InstagramConfig, method: str, path: str,
    *, data: dict | None = None, params: dict | None = None,
) -> dict:
    if method == "GET":
        response = safe_get(client, f"{config.base_url}/{path}",
                            headers={"Authorization": f"Bearer {config.access_token}"}, params=params)
        return response_payload(response, "Instagram", config.access_token)
    try:
        response = client.request(
            method, f"{config.base_url}/{path}",
            headers={"Authorization": f"Bearer {config.access_token}"},
            data=data, params=params, follow_redirects=False,
        )
    except httpx.RequestError:
        raise click.ClickException("Instagram: Netzwerkfehler bei der Veröffentlichung.") from None
    return response_payload(response, "Instagram", config.access_token)


def require_id(payload: dict) -> str:
    media_id = payload.get("id")
    if not isinstance(media_id, (str, int)) or not str(media_id).isdigit():
        raise RuntimeError("Instagram hat keine gültige Medien-ID zurückgegeben.")
    return str(media_id)


def validate_image(client: httpx.Client, event: dict) -> str:
    image_url = get_image_url(event)
    if not image_url:
        raise ValueError("Instagram benötigt ein Hauptbild; ein Textbeitrag ist nicht möglich.")
    with media_response(client, image_url) as response:
        prefix = b""
        for chunk in response.iter_bytes():
            prefix += chunk
            if len(prefix) >= 3:
                break
        if not prefix.startswith(b"\xff\xd8\xff"):
            raise ValueError("Instagram benötigt ein öffentlich abrufbares JPEG. Das Hauptbild ist kein JPEG.")
    return str(response.url)


def wait_for_container(client: httpx.Client, config: InstagramConfig, container_id: str) -> None:
    for attempt in range(POLL_ATTEMPTS):
        payload = instagram_request(client, config, "GET", container_id, params={"fields": "status_code,status"})
        status = payload.get("status_code")
        if status == "FINISHED":
            return
        if status != "IN_PROGRESS":
            raise RuntimeError("Instagram-Container: " + redact(str(payload), config.access_token))
        if attempt < POLL_ATTEMPTS - 1:
            click.echo("Instagram verarbeitet das Bild; nächste Prüfung in 60 Sekunden.")
            time.sleep(POLL_INTERVAL)
    raise RuntimeError("Instagram-Bildverarbeitung nicht rechtzeitig abgeschlossen; nichts veröffentlicht.")


def publish_instagram_photo(
    client: httpx.Client, config: InstagramConfig, image_url: str, caption: str,
) -> str:
    container = instagram_request(client, config, "POST", f"{config.user_id}/media",
                                  data={"image_url": image_url, "caption": caption})
    container_id = require_id(container)
    wait_for_container(client, config, container_id)
    published = instagram_request(client, config, "POST", f"{config.user_id}/media_publish",
                                  data={"creation_id": container_id})
    return require_id(published)


def publish_event(client: httpx.Client, conn: sqlite3.Connection, event: dict, dry_run: bool,
                  *, config: InstagramConfig | None = None) -> bool:
    caption = build_instagram_caption(event)
    click.echo("\n" + "=" * 80)
    click.echo(caption)
    click.echo(f"\nZeichen: {len(caption)}/{CAPTION_LIMIT}")
    click.echo(f"🖼 {get_image_url(event) or 'Kein Hauptbild vorhanden'}")
    click.echo("=" * 80)
    image_url = validate_image(client, event)
    if dry_run:
        click.secho("DRY RUN: kein Instagram-Post veröffentlicht.", fg="yellow")
        return False
    if not click.confirm("Diesen Termin jetzt auf Instagram veröffentlichen?", default=False):
        click.echo("Übersprungen.")
        return False
    config = config or authenticate()
    media_id = publish_instagram_photo(client, config, image_url, caption)
    # Persist immediately after confirmation from Meta, without optional API reads.
    remember_post(conn, event, media_id)
    click.secho(f"Instagram-Post erstellt: {media_id}", fg="green")
    return True


def authenticate() -> InstagramConfig:
    config = load_config(allow_prompt=True)
    check_auth(config)
    if config.primary:
        persist_validated_meta(config.primary)
    return config


@click.command("instagram", help="Kulturbytes-Termine für Instagram auswählen, prüfen und veröffentlichen.")
@credential_options("Instagram")
@click.option("--check-auth", "check_auth_only", is_flag=True, help="Nur Zugang und Zielkonto prüfen; hat Vorrang vor Auswahl und Veröffentlichung.")
@click.option("--dry-run/--publish", default=True, help="Vorschau (Standard) oder nach Bestätigung veröffentlichen.")
@click.option("--limit", type=click.IntRange(min=0), default=50, show_default=True, help="Termine in der Auswahl; 0 zeigt alle.")
@click.option("--include-published", is_flag=True, help="Bereits veröffentlichte Termine mit zusätzlicher Rückfrage anbieten.")
@click.option("--city", default=None, help="Nach Stadt filtern, z.B. Flensburg.")
@click.option("--event-uuid", default=None, help="Event-UUID für die direkte Terminauswahl.")
@click.option("--date-identifier", default=None, help="Termin-Slug oder Termin-UUID; benötigt --event-uuid.")
def instagram_command(check_auth_only: bool, dry_run: bool, limit: int, include_published: bool, city: str | None,
         event_uuid: str | None, date_identifier: str | None) -> None:
    if check_auth_only:
        authenticate()
        return
    config = authenticate() if not dry_run else None

    def publish_with_config(client: httpx.Client, conn: sqlite3.Connection, event: dict, *, dry_run: bool) -> bool:
        return publish_event(client, conn, event, dry_run=dry_run, config=config)

    run_publisher(
        conn=init_database(), publish_event=publish_with_config,
        user_agent="Kulturbytes-Instagram-Publisher/1.0", dry_run=dry_run,
        limit=limit, include_published=include_published, city=city,
        event_uuid=event_uuid, date_identifier=date_identifier,
    )
