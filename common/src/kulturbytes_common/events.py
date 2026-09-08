import re
import unicodedata
from datetime import date, datetime
from .timezone import TIMEZONE, application_today

import httpx

KULTURBYTES_EVENTS_API = "https://api.kulturbytes.de/api/events"
KULTURBYTES_EVENT_API = "https://api.kulturbytes.de/api/event"


def get_events(
    client: httpx.Client,
) -> list[dict]:
    response = client.get(
        KULTURBYTES_EVENTS_API,
    )

    response.raise_for_status()

    payload = response.json()

    return payload["data"]["events"]


def get_event_details(
    client: httpx.Client,
    event: dict,
) -> dict:
    event_uuid = event["uuid"]
    date_slug = event["date_slug"]

    url = (
        f"{KULTURBYTES_EVENT_API}/"
        f"{event_uuid}/date/{date_slug}"
    )

    response = client.get(url)
    response.raise_for_status()

    payload = response.json()

    return payload["data"]


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

    return event_date >= application_today()


def get_event_url(
    event: dict,
) -> str:
    event_uuid = event["uuid"]
    date_slug = event["date"]["slug"]

    return (
        "https://kulturbytes.de/de/veranstaltung/"
        f"{event_uuid}/"
        f"{date_slug}"
    )


def get_start_datetime(
    event: dict,
) -> datetime:
    event_date = event["date"]

    start_date = event_date["start_date"]

    start_time = (
        event_date.get("start_time")
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
    event_date = event["date"]

    parts: list[str] = []

    street = event_date.get(
        "venue_street"
    )

    house_number = event_date.get(
        "venue_house_number"
    )

    if street:
        street_line = street.strip()

        if house_number:
            street_line += (
                f" {house_number.strip()}"
            )

        parts.append(street_line)

    postal_code = event_date.get(
        "venue_postal_code"
    )

    city = event_date.get(
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


def normalize_hashtag(
    value: str,
) -> str | None:
    if not value:
        return None

    value = value.strip()

    if not value:
        return None

    value = unicodedata.normalize(
        "NFC",
        value,
    )

    value = re.sub(
        r"[\s\-_/]+",
        "",
        value,
    )

    value = re.sub(
        r"[^\wÄÖÜäöüß]",
        "",
        value,
        flags=re.UNICODE,
    )

    if not value:
        return None

    return f"#{value}"


def build_hashtags(
    event: dict,
) -> str:
    hashtags: list[str] = []

    tags = event.get("tags") or []

    for tag in tags:
        hashtag = normalize_hashtag(tag)

        if hashtag:
            hashtags.append(hashtag)

    hashtags.append("#Kulturbytes")

    city = (
        event.get("date", {})
        .get("venue_city")
    )

    city_hashtag = normalize_hashtag(
        city or ""
    )

    if city_hashtag:
        hashtags.append(
            city_hashtag
        )

    seen: set[str] = set()
    unique: list[str] = []

    for hashtag in hashtags:
        key = hashtag.casefold()

        if key in seen:
            continue

        seen.add(key)
        unique.append(hashtag)

    return " ".join(unique)


def format_price(
    event: dict,
) -> str | None:
    event_date = event["date"]

    price_type = event_date.get(
        "price_type"
    )

    if price_type == "free":
        return "Eintritt frei"

    min_price = event_date.get(
        "min_price"
    )

    max_price = event_date.get(
        "max_price"
    )

    currency = event_date.get(
        "currency",
        "EUR",
    )

    if min_price is None:
        return None

    if (
        max_price is not None
        and max_price != min_price
    ):
        return (
            f"Eintritt: "
            f"{min_price:g}–{max_price:g} "
            f"{currency}"
        )

    return (
        f"Eintritt: "
        f"{min_price:g} "
        f"{currency}"
    )
