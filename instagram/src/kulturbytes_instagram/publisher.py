"""Publish Kulturbytes event photos through the Instagram Content Publishing API."""

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import click
import httpx
from kulturbytes_common.auth import remote_identifier
from kulturbytes_common.publications import begin_remote_mutation
from kulturbytes_common.http import safe_get

from kulturbytes_common.auth import check_auth_request, redact, response_payload
from kulturbytes_common.credentials import (
    INSTAGRAM, resolve_credential, warn_legacy, meta_candidate, persist_validated_meta,
)
from kulturbytes_common.environment import ResolvedValue, get_config
from kulturbytes_common.events import (
    build_address, build_hashtags, format_price, get_event_url, get_start_datetime,
)
from kulturbytes_common.formatting import strip_markdown
from kulturbytes_common.media import get_image_url
from kulturbytes_common.media_security import media_response

CAPTION_LIMIT = 2200
HASHTAG_LIMIT = 5  # Conservative application cap, including Kulturbytes and city.
POLL_ATTEMPTS = 5
POLL_INTERVAL = 60


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
        raise click.ClickException("Instagram: Titel/Metadaten sind zu lang; Link und Hashtags werden nicht abgeschnitten.")
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


def require_id(payload: dict, token: str = "") -> str:
    media_id = payload.get("id")
    if not isinstance(media_id, (str, int)) or not str(media_id).isdigit():
        raise RuntimeError("Instagram hat keine gültige Medien-ID zurückgegeben.")
    return remote_identifier(media_id, "Instagram", token)


def validate_image(client: httpx.Client, event: dict) -> str:
    image_url = get_image_url(event)
    if not image_url:
        raise click.ClickException("Instagram benötigt ein Hauptbild; ein Textbeitrag ist nicht möglich.")
    with media_response(client, image_url) as response:
        prefix = b""
        for chunk in response.iter_bytes():
            prefix += chunk
            if len(prefix) >= 3:
                break
        if not prefix.startswith(b"\xff\xd8\xff"):
            raise click.ClickException("Instagram benötigt ein öffentlich abrufbares JPEG. Das Hauptbild ist kein JPEG.")
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
    begin_remote_mutation("instagram_container")
    container = instagram_request(client, config, "POST", f"{config.user_id}/media",
                                  data={"image_url": image_url, "caption": caption})
    container_id = require_id(container, config.access_token)
    wait_for_container(client, config, container_id)
    begin_remote_mutation("instagram_publish")
    published = instagram_request(client, config, "POST", f"{config.user_id}/media_publish",
                                  data={"creation_id": container_id})
    return require_id(published, config.access_token)




def authenticate() -> InstagramConfig:
    config = load_config(allow_prompt=False)
    check_auth(config)
    if config.primary:
        persist_validated_meta(config.primary)
    return config
