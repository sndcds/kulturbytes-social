#!/usr/bin/env python3

import os
import sqlite3
from datetime import date
from pathlib import Path

import click
import httpx

from kulturbytes_common.events import (
    build_address, build_hashtags, format_price, get_event_url, get_start_datetime,
)
from kulturbytes_common.media import download_image, get_image_url
from kulturbytes_common.workflow import run_publisher


FACEBOOK_PAGE_ID = os.environ["FACEBOOK_PAGE_ID"]
FACEBOOK_PAGE_ACCESS_TOKEN = os.environ["FACEBOOK_PAGE_ACCESS_TOKEN"]

FACEBOOK_GRAPH_API_VERSION = os.getenv(
    "FACEBOOK_GRAPH_API_VERSION",
    "v26.0",
)

DATABASE_PATH = Path(
    os.getenv(
        "DATABASE_PATH",
        "facebook_posts.sqlite3",
    )
)


def init_database() -> sqlite3.Connection:
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
        event.get("description")
        or event.get("summary")
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


def facebook_request_error(
    response: httpx.Response,
) -> None:
    click.echo()
    click.echo(
        "Facebook API error:"
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


def publish_facebook_photo(
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
        "https://graph.facebook.com/"
        f"{FACEBOOK_GRAPH_API_VERSION}/"
        f"{FACEBOOK_PAGE_ID}/photos"
    )

    response = client.post(
        url,
        data={
            "caption": build_message(
                event
            ),
            "access_token": (
                FACEBOOK_PAGE_ACCESS_TOKEN
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

    if response.is_error:
        facebook_request_error(
            response
        )

        response.raise_for_status()

    payload = response.json()

    post_id = (
        payload.get("post_id")
        or payload.get("id")
    )

    if not post_id:
        raise RuntimeError(
            "Facebook hat keine "
            "Post-ID zurückgegeben: "
            f"{payload}"
        )

    return str(
        post_id
    )


def publish_text_post(
    client: httpx.Client,
    event: dict,
) -> str:
    url = (
        "https://graph.facebook.com/"
        f"{FACEBOOK_GRAPH_API_VERSION}/"
        f"{FACEBOOK_PAGE_ID}/feed"
    )

    response = client.post(
        url,
        data={
            "message": build_message(
                event
            ),
            "access_token": (
                FACEBOOK_PAGE_ACCESS_TOKEN
            ),
        },
    )

    if response.is_error:
        facebook_request_error(
            response
        )

        response.raise_for_status()

    payload = response.json()

    post_id = payload.get(
        "id"
    )

    if not post_id:
        raise RuntimeError(
            "Facebook hat keine "
            "Post-ID zurückgegeben: "
            f"{payload}"
        )

    return str(
        post_id
    )


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


@click.command()
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
def main(
    dry_run: bool,
    limit: int,
    include_published: bool,
    city: str | None,
) -> None:
    run_publisher(
        conn=init_database(),
        publish_event=publish_event,
        user_agent="Kulturbytes-Facebook-Publisher/1.2",
        dry_run=dry_run,
        limit=limit,
        include_published=include_published,
        city=city,
    )


if __name__ == "__main__":
    main()
