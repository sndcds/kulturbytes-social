#!/usr/bin/env python3

import re
from dataclasses import dataclass, field

import click
import httpx
from kulturbytes_common.auth import remote_identifier
from kulturbytes_common.publications import begin_remote_mutation

from kulturbytes_common.auth import redact, response_payload
from kulturbytes_facebook.auth import authenticate_page
from kulturbytes_common.credentials import FACEBOOK_PAGE, resolve_credential
from kulturbytes_common.environment import get_config
from kulturbytes_common.events import (
    build_address, build_hashtags, format_price, get_event_url, get_start_datetime,
)
from kulturbytes_common.media import download_image, get_image_url


@dataclass(frozen=True)
class FacebookConfig:
    page_id: str
    access_token: str = field(repr=False)
    graph_api_version: str
    secrets: tuple[str, ...] = field(default=(), repr=False)


def load_settings() -> tuple[str, str]:
    page_id = get_config("FACEBOOK_PAGE_ID", "").strip()
    version = get_config("FACEBOOK_GRAPH_API_VERSION", "v26.0").strip()
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


def authenticate(*, force: bool = False, allow_prompt: bool = False) -> FacebookConfig:
    page_id, version = load_settings()
    secrets: list[str] = []
    token = authenticate_page(page_id, version, force=force, secrets=secrets, allow_prompt=allow_prompt)
    return FacebookConfig(page_id, token, version, tuple(secrets))








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




def publish_facebook_photo(
    client: httpx.Client,
    event: dict,
    *, config: FacebookConfig | None = None, message: str | None = None,
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

    begin_remote_mutation("facebook_photo")
    response = client.post(
        url,
        headers={"Authorization": f"Bearer {config.access_token}"},
        follow_redirects=False,
        data={
            "caption": build_message(event) if message is None else message,
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

    return remote_identifier(post_id, "Facebook", config.access_token)


def publish_text_post(
    client: httpx.Client,
    event: dict,
    *, config: FacebookConfig | None = None, message: str | None = None,
) -> str:
    config = config or load_config()
    url = (
        "https://graph.facebook.com/"
        f"{config.graph_api_version}/"
        f"{config.page_id}/feed"
    )

    begin_remote_mutation("facebook_feed")
    response = client.post(
        url,
        headers={"Authorization": f"Bearer {config.access_token}"},
        follow_redirects=False,
        data={
            "message": build_message(event) if message is None else message,
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

    return remote_identifier(post_id, "Facebook", config.access_token)
