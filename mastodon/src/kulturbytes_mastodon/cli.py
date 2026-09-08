#!/usr/bin/env python3

import os
import sqlite3
import time
from datetime import date
from pathlib import Path

import click
import httpx

from kulturbytes_common.events import (
    build_hashtags, format_price, get_event_url, get_start_datetime,
)
from kulturbytes_common.formatting import strip_markdown
from kulturbytes_common.media import download_image, get_image_url
from kulturbytes_common.workflow import run_publisher


MASTODON_BASE_URL = os.getenv(
    "MASTODON_BASE_URL",
    "https://norden.social",
).rstrip("/")

MASTODON_ACCESS_TOKEN = os.environ["MASTODON_ACCESS_TOKEN"]

DATABASE_PATH = Path(
    os.getenv(
        "DATABASE_PATH",
        "mastodon_posts.sqlite3",
    )
)


def init_database() -> sqlite3.Connection:
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


def build_mastodon_message(
    event: dict,
    max_length: int = 500,
) -> str:
    event_date = event["date"]

    title = strip_markdown(
        event.get("title", "")
    )

    subtitle = strip_markdown(
        event.get("subtitle") or ""
    )

    summary = strip_markdown(
        event.get("summary")
        or event.get("description")
        or ""
    )

    start = get_start_datetime(event)

    venue = strip_markdown(
        event_date.get("venue_name") or ""
    )

    city = strip_markdown(
        event_date.get("venue_city") or ""
    )

    event_url = get_event_url(event)
    hashtags = build_hashtags(event)

    header: list[str] = [
        f"📅 {title}",
    ]

    if subtitle:
        header.append(subtitle)

    date_line = (
        f"🗓 {start.strftime('%d.%m.%Y')} "
        f"· {start.strftime('%H:%M')} Uhr"
    )

    end_date = event_date.get("end_date")

    if (
        end_date
        and end_date != event_date["start_date"]
    ):
        end = date.fromisoformat(end_date)

        date_line += (
            f" – {end.strftime('%d.%m.%Y')}"
        )

    header.append(date_line)

    location_parts: list[str] = []

    if venue:
        location_parts.append(venue)

    if city and city.casefold() != venue.casefold():
        location_parts.append(city)

    if location_parts:
        header.append(
            "📍 " + ", ".join(location_parts)
        )

    footer: list[str] = []

    price = format_price(event)

    if price:
        footer.append(price)

    ticket_link = event_date.get(
        "ticket_link"
    )

    if ticket_link:
        footer.append(
            f"🎟 {ticket_link}"
        )

    footer.append(
        f"👉 {event_url}"
    )

    if hashtags:
        footer.append(
            hashtags
        )

    header_text = "\n".join(header)
    footer_text = "\n".join(footer)

    # Leerzeilen zwischen den Bereichen
    fixed_text = (
        f"{header_text}\n\n"
        f"{footer_text}"
    )

    # Reserve für:
    # \n\n + Zusammenfassung + …
    available = (
        max_length
        - len(fixed_text)
        - 3
    )

    if summary and available > 20:
        if len(summary) > available:
            summary = (
                summary[: available - 1]
                .rsplit(" ", 1)[0]
                .rstrip(" ,.;:-")
                + "…"
            )

        message = (
            f"{header_text}\n\n"
            f"{summary}\n\n"
            f"{footer_text}"
        )

    else:
        message = fixed_text

    # Letzte Sicherheitsstufe
    if len(message) > max_length:
        message = message[:max_length]

    return message


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
) -> None:
    click.echo()
    click.echo("=" * 80)

    message = build_mastodon_message(
        event,
        max_length=500,
    )

    click.echo(message)

    click.echo()
    click.echo(
        f"Zeichen: {len(message)}/500"
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


def mastodon_request_error(
    response: httpx.Response,
) -> None:
    click.echo()
    click.echo(
        "Mastodon API error:"
    )

    click.echo(
        f"Status: {response.status_code}"
    )

    try:
        click.echo(
            str(response.json())
        )
    except ValueError:
        click.echo(
            response.text
        )


def wait_for_media(
    client: httpx.Client,
    media_id: str,
) -> None:
    url = (
        f"{MASTODON_BASE_URL}"
        f"/api/v1/media/{media_id}"
    )

    for _ in range(10):
        response = client.get(
            url,
            headers={
                "Authorization": (
                    f"Bearer "
                    f"{MASTODON_ACCESS_TOKEN}"
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
) -> str:
    (
        image_bytes,
        content_type,
        filename,
    ) = download_image(
        client,
        event,
    )

    url = (
        f"{MASTODON_BASE_URL}"
        "/api/v2/media"
    )

    response = client.post(
        url,
        headers={
            "Authorization": (
                f"Bearer "
                f"{MASTODON_ACCESS_TOKEN}"
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

    if response.is_error:
        mastodon_request_error(
            response
        )
        response.raise_for_status()

    payload = response.json()

    media_id = payload.get("id")

    if not media_id:
        raise RuntimeError(
            "Mastodon hat keine "
            "Media-ID zurückgegeben: "
            f"{payload}"
        )

    return str(media_id)


def publish_mastodon_status(
    client: httpx.Client,
    event: dict,
) -> tuple[str, str | None]:
    media_id = None

    if get_image_url(event):
        media_id = upload_mastodon_media(client, event)
        wait_for_media(client, media_id)

    data = {
        "status": build_mastodon_message(
            event,
            max_length=500,
        ),
        "visibility": "public",
    }

    if media_id:
        data["media_ids[]"] = media_id

    response = client.post(
        f"{MASTODON_BASE_URL}/api/v1/statuses",
        headers={
            "Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}",
        },
        data=data,
    )

    if response.is_error:
        mastodon_request_error(response)

    response.raise_for_status()
    payload = response.json()
    status_id = payload.get("id")

    if not status_id:
        raise RuntimeError(
            "Mastodon hat keine Status-ID zurückgegeben: "
            f"{payload}"
        )

    return str(status_id), payload.get("url")


def publish_event(
    client: httpx.Client,
    conn: sqlite3.Connection,
    event: dict,
    dry_run: bool,
) -> bool:
    print_event_preview(
        event
    )

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


@click.command()
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
def main(
    dry_run: bool,
    limit: int,
    include_published: bool,
    city: str | None,
    event_uuid: str | None,
    date_identifier: str | None,
) -> None:
    run_publisher(
        conn=init_database(),
        publish_event=publish_event,
        user_agent="Kulturbytes-Mastodon-Publisher/1.0",
        dry_run=dry_run,
        limit=limit,
        include_published=include_published,
        city=city,
        event_uuid=event_uuid,
        date_identifier=date_identifier,
    )


if __name__ == "__main__":
    main()
