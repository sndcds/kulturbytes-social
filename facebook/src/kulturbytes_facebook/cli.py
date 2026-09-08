#!/usr/bin/env python3

import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date

import click
import httpx

from kulturbytes_common.auth import redact, response_payload
from kulturbytes_facebook.auth import authenticate_page
from kulturbytes_common.credentials import FACEBOOK_PAGE, credential_options, resolve_credential
from kulturbytes_common.database import get_database_path
from kulturbytes_common.events import (
    build_address, build_hashtags, format_price, get_event_url, get_start_datetime,
)
from kulturbytes_common.media import download_image, get_image_url
from kulturbytes_common.workflow import run_publisher


@dataclass(frozen=True)
class FacebookConfig:
    page_id: str
    access_token: str = field(repr=False)
    graph_api_version: str
    secrets: tuple[str, ...] = field(default=(), repr=False)


def load_settings() -> tuple[str, str]:
    page_id = os.getenv("FACEBOOK_PAGE_ID", "").strip()
    version = os.getenv("FACEBOOK_GRAPH_API_VERSION", "v26.0").strip()
    if not page_id:
        raise click.ClickException("FACEBOOK_PAGE_ID fehlt.")
    if not page_id.isascii() or not page_id.isdigit():
        raise click.ClickException("FACEBOOK_PAGE_ID muss eine numerische Seiten-ID sein.")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+", version):
        raise click.ClickException("FACEBOOK_GRAPH_API_VERSION muss z.B. v26.0 sein.")
    return page_id, version


def load_config() -> FacebookConfig:
    page_id, version = load_settings()
    token = resolve_credential(FACEBOOK_PAGE)
    if not token:
        raise click.ClickException("FACEBOOK_PAGE_ACCESS_TOKEN fehlt.")
    return FacebookConfig(page_id, token, version)


def authenticate(*, force: bool = False) -> FacebookConfig:
    page_id, version = load_settings()
    secrets: list[str] = []
    token = authenticate_page(page_id, version, force=force, secrets=secrets)
    return FacebookConfig(page_id, token, version, tuple(secrets))


DATABASE_PATH = get_database_path("facebook")


def init_database() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS published_events (
            date_uuid TEXT PRIMARY KEY,
            event_uuid TEXT NOT NULL,
            facebook_post_id TEXT NOT NULL,
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
    facebook_post_id: str,
) -> None:
    event_date = event["date"]

    conn.execute(
        """
        INSERT INTO published_events (
            date_uuid,
            event_uuid,
            facebook_post_id,
            title,
            start_date,
            start_time
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(date_uuid) DO UPDATE SET
            event_uuid = excluded.event_uuid,
            facebook_post_id = excluded.facebook_post_id,
            title = excluded.title,
            start_date = excluded.start_date,
            start_time = excluded.start_time,
            published_at = CURRENT_TIMESTAMP
        """,
        (
            event_date["uuid"],
            event["uuid"],
            facebook_post_id,
            event["title"],
            event_date["start_date"],
            event_date.get("start_time"),
        ),
    )

    conn.commit()


def build_message(
    event: dict,
) -> str:
    lines: list[str] = []

    event_date = event["date"]

    title = event["title"]

    subtitle = event.get(
        "subtitle"
    )

    description = (
        event.get("summary")
        or event.get("description")
    )

    start = get_start_datetime(
        event
    )

    venue = event_date.get(
        "venue_name"
    )

    address = build_address(
        event
    )

    organization = event.get(
        "org_name"
    )

    lines.append(
        f"📅 {title}"
    )

    if subtitle:
        lines.extend(
            [
                "",
                subtitle.strip(),
            ]
        )

    lines.extend(
        [
            "",
            (
                "🗓 "
                f"{start.strftime('%d.%m.%Y')}"
                " · "
                f"{start.strftime('%H:%M')} Uhr"
            ),
        ]
    )

    end_date = event_date.get(
        "end_date"
    )

    if (
        end_date
        and end_date
        != event_date["start_date"]
    ):
        end = date.fromisoformat(
            end_date
        )

        lines.append(
            f"bis {end.strftime('%d.%m.%Y')}"
        )

    if venue:
        lines.append(
            f"📍 {venue}"
        )

    if address:
        lines.append(
            address
        )

    if description:
        lines.extend(
            [
                "",
                description.strip(),
            ]
        )

    if organization:
        lines.extend(
            [
                "",
                (
                    "Veranstalter: "
                    f"{organization}"
                ),
            ]
        )

    price = format_price(
        event
    )

    if price:
        lines.extend(
            [
                "",
                price,
            ]
        )

    ticket_link = event_date.get(
        "ticket_link"
    )

    if ticket_link:
        lines.extend(
            [
                "",
                (
                    "🎟 Tickets: "
                    f"{ticket_link}"
                ),
            ]
        )

    lines.extend(
        [
            "",
            (
                "👉 Mehr Informationen: "
                f"{get_event_url(event)}"
            ),
        ]
    )

    hashtags = build_hashtags(
        event
    )

    if hashtags:
        lines.extend(
            [
                "",
                hashtags,
            ]
        )

    return "\n".join(lines)


def print_event_preview(
    event: dict,
) -> None:
    click.echo()
    click.echo("=" * 80)

    click.echo(
        build_message(event)
    )

    image_url = get_image_url(
        event
    )

    if image_url:
        click.echo()
        click.echo(
            f"🖼 {image_url}"
        )

    click.echo("=" * 80)


def publish_facebook_photo(
    client: httpx.Client,
    event: dict,
    *, config: FacebookConfig | None = None,
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
        "https://graph.facebook.com/"
        f"{config.graph_api_version}/"
        f"{config.page_id}/photos"
    )

    response = client.post(
        url,
        headers={"Authorization": f"Bearer {config.access_token}"},
        follow_redirects=False,
        data={
            "caption": build_message(
                event
            ),
        },
        files={
            "source": (
                filename,
                image_bytes,
                content_type,
            ),
        },
    )

    payload = response_payload(response, "Facebook", config.access_token)

    post_id = (
        payload.get("post_id")
        or payload.get("id")
    )

    if not post_id:
        raise RuntimeError(
            "Facebook hat keine "
            "Post-ID zurückgegeben: "
            + redact(str(payload), config.access_token)
        )

    return str(
        post_id
    )


def publish_text_post(
    client: httpx.Client,
    event: dict,
    *, config: FacebookConfig | None = None,
) -> str:
    config = config or load_config()
    url = (
        "https://graph.facebook.com/"
        f"{config.graph_api_version}/"
        f"{config.page_id}/feed"
    )

    response = client.post(
        url,
        headers={"Authorization": f"Bearer {config.access_token}"},
        follow_redirects=False,
        data={
            "message": build_message(
                event
            ),
        },
    )

    payload = response_payload(response, "Facebook", config.access_token)

    post_id = payload.get(
        "id"
    )

    if not post_id:
        raise RuntimeError(
            "Facebook hat keine "
            "Post-ID zurückgegeben: "
            + redact(str(payload), config.access_token)
        )

    return str(
        post_id
    )


def publish_event(
    client: httpx.Client,
    conn: sqlite3.Connection,
    event: dict,
    dry_run: bool,
    *, config: FacebookConfig | None = None,
) -> bool:
    print_event_preview(
        event
    )

    if dry_run:
        click.secho(
            "DRY RUN: kein Facebook-Post veröffentlicht.",
            fg="yellow",
        )

        return False

    if not click.confirm(
        "Diesen Termin jetzt auf Facebook veröffentlichen?",
        default=False,
    ):
        click.echo(
            "Übersprungen."
        )

        return False

    if get_image_url(
        event
    ):
        facebook_post_id = (
            publish_facebook_photo(
                client,
                event,
                config=config,
            )
        )

        click.secho(
            (
                "Facebook-Fotopost erstellt: "
                f"{facebook_post_id}"
            ),
            fg="green",
        )

    else:
        click.echo(
            "Kein Eventbild vorhanden. "
            "Erstelle Textpost."
        )

        facebook_post_id = (
            publish_text_post(
                client,
                event,
                config=config,
            )
        )

        click.secho(
            (
                "Facebook-Textpost erstellt: "
                f"{facebook_post_id}"
            ),
            fg="green",
        )

    remember_post(
        conn,
        event,
        facebook_post_id,
    )

    click.echo(
        "Gespeichert: "
        f"{event['date']['uuid']} "
        f"-> {facebook_post_id}"
    )

    return True


@click.command("facebook", help="Kulturbytes-Termine für Facebook auswählen, prüfen und veröffentlichen.")
@credential_options("Facebook")
@click.option("--resolve-page-token", is_flag=True, help="Veraltet: Legacy-Page-Token ableiten; mit Meta-Token identisch zu --check-auth.")
@click.option("--check-auth", "check_auth_only", is_flag=True, help="Nur Zugang und Zielkonto prüfen; hat Vorrang vor Auswahl und Veröffentlichung.")
@click.option(
    "--dry-run/--publish",
    default=True,
    help=(
        "Im Dry-Run-Modus nur Vorschau anzeigen. "
        "Mit --publish echte Facebook-Posts erstellen."
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
def facebook_command(
    check_auth_only: bool,
    resolve_page_token: bool,
    dry_run: bool,
    limit: int,
    include_published: bool,
    city: str | None,
    event_uuid: str | None,
    date_identifier: str | None,
) -> None:
    if check_auth_only or resolve_page_token:
        authenticate(force=resolve_page_token)
        return
    config = authenticate() if not dry_run else None

    def publish_with_config(client: httpx.Client, conn: sqlite3.Connection, event: dict, *, dry_run: bool) -> bool:
        try:
            return publish_event(client, conn, event, dry_run=dry_run, config=config)
        except httpx.RequestError:
            raise click.ClickException("Facebook: Netzwerkfehler bei der Veröffentlichung.") from None
        except Exception as exc:
            message = str(exc)
            for secret in config.secrets if config else ():
                message = redact(message, secret)
            raise click.ClickException(message) from None
    run_publisher(
        conn=init_database(),
        publish_event=publish_with_config,
        user_agent="Kulturbytes-Facebook-Publisher/1.2",
        dry_run=dry_run,
        limit=limit,
        include_published=include_published,
        city=city,
        event_uuid=event_uuid,
        date_identifier=date_identifier,
    )
