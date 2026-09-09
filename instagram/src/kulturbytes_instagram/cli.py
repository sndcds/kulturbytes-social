"""Publish canonical photos through the Instagram Content Publishing API."""

import re
import sqlite3
import time
from dataclasses import dataclass, field
from functools import partial
from urllib.parse import urlsplit

import click
import httpx

from kulturbytes_common import storage
from kulturbytes_common.auth import (
    check_auth_request,
    redact,
    remote_identifier,
    response_payload,
)
from kulturbytes_common.credentials import (
    INSTAGRAM,
    credential_options,
    meta_candidate,
    persist_validated_meta,
    resolve_credential,
    warn_legacy,
)
from kulturbytes_common.environment import ResolvedValue, get_config
from kulturbytes_common.http import safe_get
from kulturbytes_common.media import post_image_url
from kulturbytes_common.media_security import media_response
from kulturbytes_common.publications import begin_remote_mutation, execute_publication
from kulturbytes_common.rendering import render_post
from kulturbytes_common.sources.cli import DEFAULT_SOURCE, prepare_source
from kulturbytes_common.sources.models import ContentItem
from kulturbytes_common.workflow import run_publisher

CAPTION_LIMIT = 2200
HASHTAG_LIMIT = 5  # Conservative application cap for all sources.
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
    login = (
        get_config("INSTAGRAM_LOGIN_TYPE", "facebook" if system_token else "instagram")
        .strip()
        .lower()
    )
    if system_token and login == "instagram":
        raise click.ClickException(
            "META_SYSTEM_USER_ACCESS_TOKEN benötigt INSTAGRAM_LOGIN_TYPE=facebook; Instagram Login ist nur mit Legacy-Token möglich."
        )
    if not system_token and token:
        warn_legacy("Instagram")
    version = get_config("INSTAGRAM_GRAPH_API_VERSION", "v26.0").strip()
    if not user_id or not token:
        raise click.ClickException(
            "INSTAGRAM_USER_ID und/oder Meta-Zugang fehlen (META_SYSTEM_USER_ACCESS_TOKEN; Legacy: INSTAGRAM_ACCESS_TOKEN)."
        )
    if not user_id.isascii() or not user_id.isdigit():
        raise click.ClickException(
            "INSTAGRAM_USER_ID muss die numerische Instagram-Konto-ID sein."
        )
    hosts = {"instagram": "graph.instagram.com", "facebook": "graph.facebook.com"}
    if login not in hosts:
        raise click.ClickException(
            "INSTAGRAM_LOGIN_TYPE muss instagram oder facebook sein."
        )
    if not re.fullmatch(r"v[0-9]+\.[0-9]+", version):
        raise click.ClickException("INSTAGRAM_GRAPH_API_VERSION muss z.B. v26.0 sein.")
    return InstagramConfig(
        user_id, token, f"https://{hosts[login]}/{version}", candidate
    )


def init_database() -> sqlite3.Connection:
    return storage.init_database("instagram", DATABASE_PATH)


remember_post = partial(storage.remember_post, platform="instagram")


def build_instagram_caption(event: ContentItem) -> str:
    return render_post(event, "instagram").text


def check_auth(config: InstagramConfig) -> None:
    payload = check_auth_request(
        "Instagram",
        f"{config.base_url}/{config.user_id}",
        config.access_token,
        params={"fields": "id,username"},
    )
    if str(payload.get("id")) != config.user_id:
        raise click.ClickException(
            "Instagram: Zurückgegebene Konto-ID stimmt nicht mit INSTAGRAM_USER_ID überein."
        )
    username = payload.get("username")
    if not isinstance(username, str) or not username.strip():
        raise click.ClickException(
            "Instagram: Die Antwort enthält keinen Benutzernamen."
        )
    login = (
        "facebook"
        if urlsplit(config.base_url).hostname == "graph.facebook.com"
        else "instagram"
    )
    click.echo("✓ Instagram Token gültig")
    click.echo(redact(f"✓ Konto: @{username}", config.access_token))
    click.echo(f"✓ Login-Typ: {login}")


def instagram_request(
    client: httpx.Client,
    config: InstagramConfig,
    method: str,
    path: str,
    *,
    data: dict | None = None,
    params: dict | None = None,
) -> dict:
    if method == "GET":
        response = safe_get(
            client,
            f"{config.base_url}/{path}",
            headers={"Authorization": f"Bearer {config.access_token}"},
            params=params,
        )
        return response_payload(response, "Instagram", config.access_token)
    try:
        response = client.request(
            method,
            f"{config.base_url}/{path}",
            headers={"Authorization": f"Bearer {config.access_token}"},
            data=data,
            params=params,
            follow_redirects=False,
        )
    except httpx.RequestError:
        raise click.ClickException(
            "Instagram: Netzwerkfehler bei der Veröffentlichung."
        ) from None
    return response_payload(response, "Instagram", config.access_token)


def require_id(payload: dict, token: str = "") -> str:
    media_id = payload.get("id")
    if not isinstance(media_id, (str, int)) or not str(media_id).isdigit():
        raise RuntimeError("Instagram hat keine gültige Medien-ID zurückgegeben.")
    return remote_identifier(media_id, "Instagram", token)


def validate_image(client: httpx.Client, event: ContentItem) -> str:
    image_url = post_image_url(event, "instagram")
    if not image_url:
        raise click.ClickException(
            "Instagram benötigt ein Hauptbild; ein Textbeitrag ist nicht möglich."
        )
    with media_response(client, image_url, event.media_policy) as response:
        prefix = b""
        for chunk in response.iter_bytes():
            prefix += chunk
            if len(prefix) >= 3:
                break
        if not prefix.startswith(b"\xff\xd8\xff"):
            raise click.ClickException(
                "Instagram benötigt ein öffentlich abrufbares JPEG. Das Hauptbild ist kein JPEG."
            )
    return str(response.url)


def wait_for_container(
    client: httpx.Client, config: InstagramConfig, container_id: str
) -> None:
    for attempt in range(POLL_ATTEMPTS):
        payload = instagram_request(
            client, config, "GET", container_id, params={"fields": "status_code,status"}
        )
        status = payload.get("status_code")
        if status == "FINISHED":
            return
        if status != "IN_PROGRESS":
            raise RuntimeError(
                "Instagram-Container: " + redact(str(payload), config.access_token)
            )
        if attempt < POLL_ATTEMPTS - 1:
            click.echo(
                "Instagram verarbeitet das Bild; nächste Prüfung in 60 Sekunden."
            )
            time.sleep(POLL_INTERVAL)
    raise RuntimeError(
        "Instagram-Bildverarbeitung nicht rechtzeitig abgeschlossen; nichts veröffentlicht."
    )


def publish_instagram_photo(
    client: httpx.Client,
    config: InstagramConfig,
    image_url: str,
    caption: str,
) -> str:
    begin_remote_mutation("instagram_container")
    container = instagram_request(
        client,
        config,
        "POST",
        f"{config.user_id}/media",
        data={"image_url": image_url, "caption": caption},
    )
    container_id = require_id(container, config.access_token)
    wait_for_container(client, config, container_id)
    begin_remote_mutation("instagram_publish")
    published = instagram_request(
        client,
        config,
        "POST",
        f"{config.user_id}/media_publish",
        data={"creation_id": container_id},
    )
    return require_id(published, config.access_token)


def publish_event(
    client: httpx.Client,
    conn: sqlite3.Connection,
    event: ContentItem,
    dry_run: bool,
    *,
    config: InstagramConfig | None = None,
    allow_repeat: bool = False,
) -> bool:
    post = render_post(event, "instagram")
    caption = post.text
    click.echo("\n" + "=" * 80)
    click.echo(caption)
    click.echo(f"\nZeichen: {len(caption)}/{CAPTION_LIMIT}")
    click.echo(f"🖼 {post.image_url or 'Kein Hauptbild vorhanden'}")
    click.echo("=" * 80)
    image_url = validate_image(client, event)
    if dry_run:
        click.secho("DRY RUN: kein Instagram-Post veröffentlicht.", fg="yellow")
        return False
    if not click.confirm(
        "Diesen Inhalt jetzt auf Instagram veröffentlichen?", default=False
    ):
        click.echo("Übersprungen.")
        return False
    config = config or authenticate()
    media_id, _ = execute_publication(
        conn,
        "instagram",
        event,
        lambda: (publish_instagram_photo(client, config, image_url, caption), None),
        lambda remote_id, remote_url: remember_post(
            conn, event, remote_id, commit=False
        ),
        allow_repeat=allow_repeat,
        message=caption,
        target_ref=config.user_id,
    )
    click.secho(f"Instagram-Post erstellt: {media_id}", fg="green")
    return True


def authenticate() -> InstagramConfig:
    config = load_config(allow_prompt=True)
    check_auth(config)
    if config.primary:
        persist_validated_meta(config.primary)
    return config


@click.command(
    "instagram", help="Inhalte für Instagram auswählen, prüfen und veröffentlichen."
)
@click.option(
    "--source",
    default=DEFAULT_SOURCE,
    show_default=True,
    help="Konfigurierte JSON-Quelle.",
)
@click.option(
    "--item-id", default=None, help="Quellenneutrale ID für die direkte Auswahl."
)
@credential_options("Instagram")
@click.option(
    "--check-auth",
    "check_auth_only",
    is_flag=True,
    help="Nur Zugang und Zielkonto prüfen; hat Vorrang vor Auswahl und Veröffentlichung.",
)
@click.option(
    "--dry-run/--publish",
    default=True,
    help="Vorschau (Standard) oder nach Bestätigung veröffentlichen.",
)
@click.option(
    "--limit",
    type=click.IntRange(min=0),
    default=50,
    show_default=True,
    help="Einträge in der Auswahl; 0 zeigt alle.",
)
@click.option(
    "--include-published",
    is_flag=True,
    help="Bereits veröffentlichte Inhalte mit zusätzlicher Rückfrage anbieten.",
)
@click.option("--city", default=None, help="Nach Stadt filtern, z.B. Flensburg.")
@click.option(
    "--event-uuid",
    default=None,
    help="Kulturbytes-Kompatibilität: Event-UUID; benötigt --date-identifier.",
)
@click.option(
    "--date-identifier",
    default=None,
    help="Kulturbytes-Kompatibilität: Termin-Slug oder Termin-UUID; benötigt --event-uuid.",
)
def instagram_command(
    check_auth_only: bool,
    dry_run: bool,
    limit: int,
    include_published: bool,
    city: str | None,
    event_uuid: str | None,
    date_identifier: str | None,
    source: str = DEFAULT_SOURCE,
    item_id: str | None = None,
) -> None:
    if check_auth_only:
        authenticate()
        return
    config = authenticate() if not dry_run else None

    def publish_with_config(
        client: httpx.Client,
        conn: sqlite3.Connection,
        event: ContentItem,
        *,
        dry_run: bool,
    ) -> bool:
        return publish_event(
            client,
            conn,
            event,
            dry_run=dry_run,
            config=config,
            allow_repeat=include_published,
        )

    adapter, target = prepare_source(
        source, legacy_selector=(event_uuid, date_identifier), item_id=item_id
    )
    run_publisher(
        conn=init_database(),
        publish_item=publish_with_config,
        user_agent="Kulturbytes-Instagram-Publisher/1.0",
        dry_run=dry_run,
        limit=limit,
        include_published=include_published,
        city=city,
        adapter=adapter,
        target=target,
    )
