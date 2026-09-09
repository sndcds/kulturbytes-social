import re
import sqlite3
from dataclasses import dataclass, field
from functools import partial

import click
import httpx

from kulturbytes_common import storage
from kulturbytes_common.auth import redact, remote_identifier, response_payload
from kulturbytes_common.credentials import (
    FACEBOOK_PAGE,
    credential_options,
    resolve_credential,
)
from kulturbytes_common.environment import get_config
from kulturbytes_common.media import download_post_image as download_image
from kulturbytes_common.publications import begin_remote_mutation, execute_publication
from kulturbytes_common.rendering import render_post
from kulturbytes_common.sources.cli import DEFAULT_SOURCE, prepare_source
from kulturbytes_common.sources.models import ContentItem, RenderedPost
from kulturbytes_common.workflow import run_publisher
from kulturbytes_facebook.auth import authenticate_page


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
        raise click.ClickException(
            "FACEBOOK_PAGE_ID muss eine numerische Seiten-ID sein."
        )
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


DATABASE_PATH = None  # Optional in-process override; resolve configuration lazily.


def init_database() -> sqlite3.Connection:
    return storage.init_database("facebook", DATABASE_PATH)


remember_post = partial(storage.remember_post, platform="facebook")


def build_message(event: ContentItem) -> str:
    return render_post(event, "facebook").text


def print_event_preview(
    event: ContentItem,
    message: str | None = None,
) -> None:
    click.echo()
    click.echo("=" * 80)

    click.echo(build_message(event) if message is None else message)

    image_url = event.image_url

    if image_url:
        click.echo()
        click.echo(f"🖼 {image_url}")

    click.echo("=" * 80)


def publish_facebook_photo(
    client: httpx.Client,
    event: ContentItem | RenderedPost,
    *,
    config: FacebookConfig | None = None,
    message: str | None = None,
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
        f"https://graph.facebook.com/{config.graph_api_version}/{config.page_id}/photos"
    )

    begin_remote_mutation("facebook_photo")
    response = client.post(
        url,
        headers={"Authorization": f"Bearer {config.access_token}"},
        follow_redirects=False,
        data={
            "caption": event.text
            if isinstance(event, RenderedPost)
            else build_message(event)
            if message is None
            else message,
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

    post_id = payload.get("post_id") or payload.get("id")

    if not post_id:
        raise RuntimeError(
            "Facebook hat keine "
            "Post-ID zurückgegeben: " + redact(str(payload), config.access_token)
        )

    return remote_identifier(post_id, "Facebook", config.access_token)


def publish_text_post(
    client: httpx.Client,
    event: ContentItem | RenderedPost,
    *,
    config: FacebookConfig | None = None,
    message: str | None = None,
) -> str:
    config = config or load_config()
    url = f"https://graph.facebook.com/{config.graph_api_version}/{config.page_id}/feed"

    begin_remote_mutation("facebook_feed")
    response = client.post(
        url,
        headers={"Authorization": f"Bearer {config.access_token}"},
        follow_redirects=False,
        data={
            "message": event.text
            if isinstance(event, RenderedPost)
            else build_message(event)
            if message is None
            else message,
        },
    )

    payload = response_payload(response, "Facebook", config.access_token)

    post_id = payload.get("id")

    if not post_id:
        raise RuntimeError(
            "Facebook hat keine "
            "Post-ID zurückgegeben: " + redact(str(payload), config.access_token)
        )

    return remote_identifier(post_id, "Facebook", config.access_token)


def publish_event(
    client: httpx.Client,
    conn: sqlite3.Connection,
    event: ContentItem,
    dry_run: bool,
    *,
    config: FacebookConfig | None = None,
    allow_repeat: bool = False,
) -> bool:
    post = render_post(event, "facebook")
    message = post.text
    print_event_preview(event, message)

    if dry_run:
        click.secho(
            "DRY RUN: kein Facebook-Post veröffentlicht.",
            fg="yellow",
        )

        return False

    if not click.confirm(
        "Diesen Inhalt jetzt auf Facebook veröffentlichen?",
        default=False,
    ):
        click.echo("Übersprungen.")

        return False

    config = config or load_config()

    def publish() -> tuple[str, None]:
        publisher = publish_facebook_photo if event.image_url else publish_text_post
        return publisher(client, post, config=config, message=message), None

    facebook_post_id, _ = execute_publication(
        conn,
        "facebook",
        event,
        publish,
        lambda remote_id, remote_url: remember_post(
            conn, event, remote_id, commit=False
        ),
        allow_repeat=allow_repeat,
        message=message,
        target_ref=config.page_id,
    )
    click.secho(f"Facebook-Post erstellt: {facebook_post_id}", fg="green")
    click.echo(f"Gespeichert: {storage.item_key(event)} -> {facebook_post_id}")

    return True


@click.command(
    "facebook", help="Inhalte für Facebook auswählen, prüfen und veröffentlichen."
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
@credential_options("Facebook")
@click.option(
    "--resolve-page-token",
    is_flag=True,
    help="Veraltet: Legacy-Page-Token ableiten; mit Meta-Token identisch zu --check-auth.",
)
@click.option(
    "--check-auth",
    "check_auth_only",
    is_flag=True,
    help="Nur Zugang und Zielkonto prüfen; hat Vorrang vor Auswahl und Veröffentlichung.",
)
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
    help=("Maximale Anzahl Einträge in der Auswahl. 0 zeigt alle."),
)
@click.option(
    "--include-published",
    is_flag=True,
    help=("Auch bereits veröffentlichte Inhalte in der Auswahl anzeigen."),
)
@click.option(
    "--city",
    type=str,
    default=None,
    help=("Optional nach Stadt filtern, z.B. --city Flensburg."),
)
@click.option(
    "--event-uuid",
    type=str,
    default=None,
    help="Kulturbytes-Kompatibilität: Event-UUID; benötigt --date-identifier.",
)
@click.option(
    "--date-identifier",
    type=str,
    default=None,
    help="Kulturbytes-Kompatibilität: Termin-Slug oder Termin-UUID; benötigt --event-uuid.",
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
    source: str = DEFAULT_SOURCE,
    item_id: str | None = None,
) -> None:
    if check_auth_only or resolve_page_token:
        authenticate(force=resolve_page_token)
        return
    config = authenticate() if not dry_run else None

    def publish_with_config(
        client: httpx.Client,
        conn: sqlite3.Connection,
        event: ContentItem,
        *,
        dry_run: bool,
    ) -> bool:
        try:
            return publish_event(
                client,
                conn,
                event,
                dry_run=dry_run,
                config=config,
                allow_repeat=include_published,
            )
        except httpx.RequestError:
            raise click.ClickException(
                "Facebook: Netzwerkfehler bei der Veröffentlichung."
            ) from None
        except Exception as exc:
            message = (
                exc.format_message()
                if isinstance(exc, click.ClickException)
                else f"Veröffentlichung fehlgeschlagen ({type(exc).__name__})."
            )
            for secret in config.secrets if config else ():
                message = redact(message, secret)
            raise click.ClickException(message) from None

    adapter, target = prepare_source(
        source, legacy_selector=(event_uuid, date_identifier), item_id=item_id
    )
    run_publisher(
        conn=init_database(),
        publish_item=publish_with_config,
        user_agent="Kulturbytes-Facebook-Publisher/1.2",
        dry_run=dry_run,
        limit=limit,
        include_published=include_published,
        city=city,
        adapter=adapter,
        target=target,
    )
