#!/usr/bin/env python3

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx


KULTURBYTES_API = "https://api.kulturbytes.de/api/events"

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

DRY_RUN = (
    os.getenv("DRY_RUN", "true")
    .strip()
    .lower()
    in {"1", "true", "yes", "on"}
)

MAX_POSTS_PER_RUN = int(
    os.getenv(
        "MAX_POSTS_PER_RUN",
        "1",
    )
)

TIMEZONE = ZoneInfo("Europe/Berlin")


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


def already_published(
    conn: sqlite3.Connection,
    date_uuid: str,
) -> bool:
    row = conn.execute(
        """
        SELECT facebook_post_id
        FROM published_events
        WHERE date_uuid = ?
        """,
        (date_uuid,),
    ).fetchone()

    return row is not None


def remember_post(
    conn: sqlite3.Connection,
    event: dict,
    facebook_post_id: str,
) -> None:
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
            event["date_uuid"],
            event["uuid"],
            facebook_post_id,
            event["title"],
            event["start_date"],
            event.get("start_time"),
        ),
    )

    conn.commit()


def get_events(
    client: httpx.Client,
) -> list[dict]:
    response = client.get(
        KULTURBYTES_API,
    )

    response.raise_for_status()

    payload = response.json()

    return payload["data"]["events"]


def should_publish(
    event: dict,
) -> bool:
    if event.get("release_status") != "released":
        return False

    start_date = event.get("start_date")

    if not start_date:
        return False

    event_date = date.fromisoformat(
        start_date
    )

    if event_date < date.today():
        return False

    return True


def get_event_url(
    event: dict,
) -> str:
    return (
        "https://kulturbytes.de/de/veranstaltung/"
        f"{event['uuid']}/"
        f"{event['date_slug']}"
    )


def get_start_datetime(
    event: dict,
) -> datetime:
    start_date = event["start_date"]

    start_time = (
        event.get("start_time")
        or "00:00"
    )

    value = datetime.fromisoformat(
        f"{start_date}T{start_time}"
    )

    return value.replace(
        tzinfo=TIMEZONE
    )


def build_address(
    event: dict,
) -> str:
    parts: list[str] = []

    street = event.get(
        "venue_street"
    )

    house_number = event.get(
        "venue_house_number"
    )

    if street:
        street_line = street.strip()

        if house_number:
            street_line += (
                f" {house_number.strip()}"
            )

        parts.append(street_line)

    postal_code = event.get(
        "venue_postal_code"
    )

    city = event.get(
        "venue_city"
    )

    city_line = " ".join(
        value.strip()
        for value in [
            postal_code,
            city,
        ]
        if value
    )

    if city_line:
        parts.append(city_line)

    return ", ".join(parts)


def build_message(
    event: dict,
) -> str:
    lines: list[str] = []

    title = event["title"]

    subtitle = event.get(
        "subtitle"
    )

    summary = event.get(
        "summary"
    )

    start = get_start_datetime(
        event
    )

    venue = event.get(
        "venue_name"
    )

    address = build_address(
        event
    )

    organization = event.get(
        "org_name"
    )

    price_type = event.get(
        "price_type"
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

    if venue:
        lines.append(
            f"📍 {venue}"
        )

    if address:
        lines.append(
            address
        )

    if summary:
        lines.extend(
            [
                "",
                summary.strip(),
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

    if price_type == "free":
        lines.extend(
            [
                "",
                "Eintritt frei",
            ]
        )

    lines.extend(
        [
            "",
            (
                "👉 Mehr Informationen: "
                f"{get_event_url(event)}"
            ),
            "",
            "#Kulturbytes #Flensburg #Kultur",
        ]
    )

    return "\n".join(lines)


def print_event_preview(
    event: dict,
) -> None:
    print()
    print("=" * 80)

    print(
        build_message(event)
    )

    image_path = event.get(
        "image_path"
    )

    if image_path:
        print()
        print(
            f"🖼 {image_path}"
        )

    print("=" * 80)


def facebook_request_error(
    response: httpx.Response,
) -> None:
    print()
    print(
        "Facebook API error:"
    )

    print(
        "Status:",
        response.status_code,
    )

    try:
        payload = response.json()
    except ValueError:
        print(response.text)
        return

    print(payload)


def download_image(
    client: httpx.Client,
    event: dict,
) -> tuple[
    bytes,
    str,
    str,
]:
    image_url = event.get(
        "image_path"
    )

    if not image_url:
        raise ValueError(
            "Event besitzt kein image_path"
        )

    response = client.get(
        image_url,
    )

    response.raise_for_status()

    content_type = (
        response.headers.get(
            "content-type",
            "image/jpeg",
        )
        .split(";")[0]
        .strip()
    )

    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(
        content_type,
        ".jpg",
    )

    image_uuid = (
        event.get("image_uuid")
        or event["date_uuid"]
    )

    filename = (
        f"{image_uuid}"
        f"{extension}"
    )

    return (
        response.content,
        content_type,
        filename,
    )


def publish_facebook_photo(
    client: httpx.Client,
    event: dict,
) -> str:
    image_bytes, content_type, filename = (
        download_image(
            client,
            event,
        )
    )

    url = (
        "https://graph.facebook.com/"
        f"{FACEBOOK_GRAPH_API_VERSION}/"
        f"{FACEBOOK_PAGE_ID}/photos"
    )

    data = {
        "caption": build_message(
            event
        ),
        "access_token": (
            FACEBOOK_PAGE_ACCESS_TOKEN
        ),
    }

    files = {
        "source": (
            filename,
            image_bytes,
            content_type,
        ),
    }

    response = client.post(
        url,
        data=data,
        files=files,
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
) -> bool:
    print_event_preview(
        event
    )

    if DRY_RUN:
        print(
            "DRY RUN: "
            "kein Facebook-Post "
            "veröffentlicht."
        )

        return False

    if event.get(
        "image_path"
    ):
        facebook_post_id = (
            publish_facebook_photo(
                client,
                event,
            )
        )

        print(
            "Facebook-Fotopost "
            "erstellt:",
            facebook_post_id,
        )

    else:
        print(
            "Kein Eventbild vorhanden. "
            "Erstelle Textpost."
        )

        facebook_post_id = (
            publish_text_post(
                client,
                event,
            )
        )

        print(
            "Facebook-Textpost "
            "erstellt:",
            facebook_post_id,
        )

    remember_post(
        conn,
        event,
        facebook_post_id,
    )

    print(
        "Gespeichert:",
        event["date_uuid"],
        "->",
        facebook_post_id,
    )

    return True


def main() -> None:
    conn = init_database()

    timeout = httpx.Timeout(
        connect=10.0,
        read=60.0,
        write=60.0,
        pool=10.0,
    )

    headers = {
        "User-Agent": (
            "Kulturbytes-Facebook-"
            "Publisher/1.0"
        ),
        "Accept": (
            "application/json"
        ),
    }

    published = 0

    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
    ) as client:
        events = get_events(
            client
        )

        print(
            f"{len(events)} "
            "Kulturbytes-Termine "
            "gefunden"
        )

        events = sorted(
            events,
            key=lambda event: (
                event.get(
                    "start_date",
                    "9999-12-31",
                ),
                event.get(
                    "start_time",
                    "23:59",
                )
                or "23:59",
            ),
        )

        for event in events:
            if not should_publish(
                event
            ):
                continue

            date_uuid = event.get(
                "date_uuid"
            )

            if not date_uuid:
                print(
                    "SKIP ohne date_uuid:",
                    event.get(
                        "title",
                        "<ohne Titel>",
                    ),
                )

                continue

            if already_published(
                conn,
                date_uuid,
            ):
                print(
                    "SKIP bereits "
                    "veröffentlicht:",
                    event["title"],
                    f"({date_uuid})",
                )

                continue

            try:
                was_published = (
                    publish_event(
                        client,
                        conn,
                        event,
                    )
                )

            except httpx.HTTPStatusError:
                print(
                    "\nAbbruch wegen "
                    "Facebook API Fehler."
                )

                break

            except Exception as exc:
                print(
                    "\nFehler bei:",
                    event.get(
                        "title"
                    ),
                )

                print(
                    type(exc).__name__,
                    str(exc),
                )

                break

            if was_published:
                published += 1

            if (
                not DRY_RUN
                and published
                >= MAX_POSTS_PER_RUN
            ):
                print()
                print(
                    "Maximum für diesen "
                    "Lauf erreicht:",
                    MAX_POSTS_PER_RUN,
                )

                break
            break

    conn.close()


if __name__ == "__main__":
    main()