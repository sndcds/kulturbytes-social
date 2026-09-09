from kulturbytes_common.sources.cli import DEFAULT_SOURCE, prepare_source
from functools import partial
from kulturbytes_common import storage
from kulturbytes_common.sources.models import ContentItem, RenderedPost
from kulturbytes_common.rendering import render_post, trim_summary as trim_summary
from kulturbytes_common.media import download_post_image as download_image

import sqlite3
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import click
import httpx
from kulturbytes_common.auth import remote_identifier, remote_url
from kulturbytes_common.publications import execute_publication, begin_remote_mutation
from kulturbytes_common.http import safe_get

from kulturbytes_common.auth import check_auth_request, redact, response_payload
from kulturbytes_common.credentials import MASTODON, credential_options, resolve_credential
from kulturbytes_common.environment import get_config
from kulturbytes_common.workflow import run_publisher


@dataclass(frozen=True)
class MastodonConfig:
    base_url: str
    access_token: str = field(repr=False)


def load_base_url() -> str:
    base_url = get_config("MASTODON_BASE_URL", "https://norden.social").strip().rstrip("/")
    try:
        parsed = urlsplit(base_url)
        valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                 and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment and not parsed.path
                 and not any(character.isspace() for character in base_url))
        parsed.port  # Reject malformed port numbers too.
    except ValueError:
        valid = False
    if not valid:
        raise click.ClickException("MASTODON_BASE_URL muss eine HTTP(S)-Instanzadresse ohne Zugangsdaten, Pfad oder Query sein.")
    return base_url


def load_config() -> MastodonConfig:
    token = resolve_credential(MASTODON)
    if not token:
        raise click.ClickException("MASTODON_ACCESS_TOKEN fehlt.")
    return MastodonConfig(load_base_url(), token)


def check_auth(config: MastodonConfig) -> None:
    payload = check_auth_request(
        "Mastodon", f"{config.base_url}/api/v1/accounts/verify_credentials", config.access_token,
    )
    acct = payload.get("acct") or payload.get("username")
    if not payload.get("id") or not isinstance(acct, str) or not acct.strip():
        raise click.ClickException("Mastodon: Die Antwort enthält kein gültiges Konto.")
    if "@" not in acct:
        acct = f"{acct}@{urlsplit(config.base_url).netloc}"
    click.echo("✓ Mastodon Token gültig")
    click.echo(redact(f"✓ Konto: @{acct}", config.access_token))


DATABASE_PATH = None  # Optional in-process override; resolve configuration lazily.


def init_database() -> sqlite3.Connection:
    return storage.init_database('mastodon', DATABASE_PATH)


remember_post = partial(storage.remember_post, platform='mastodon')


DEFAULT_STATUS_LIMIT = 500


def get_status_limit(client: httpx.Client, base_url: str) -> int:
    """Read public Mastodon v2 configuration; malformed/unavailable data uses 500."""
    try:
        response = safe_get(client, f"{base_url}/api/v2/instance", follow_redirects=False)
        response.raise_for_status()
        value = response.json()
        for key in ("configuration", "statuses", "max_characters"):
            value = value.get(key) if isinstance(value, dict) else None
        if type(value) is int and value > 0:
            return value
    except (httpx.HTTPError, ValueError, click.ClickException):
        pass
    click.echo("Mastodon-Instanzlimit nicht verfügbar; verwende 500 Zeichen.", err=True)
    return DEFAULT_STATUS_LIMIT





def build_mastodon_message(event: ContentItem, max_length: int = DEFAULT_STATUS_LIMIT) -> str:
    return render_post(event, 'mastodon', max_length=max_length).text


def get_image_alt_text(event: ContentItem | RenderedPost) -> str:
    return event.image_alt or f'Bild zu {getattr(event, "title", "")}'


def print_event_preview(
    event: ContentItem,
    message: str,
    max_length: int,
) -> None:
    click.echo()
    click.echo("=" * 80)

    click.echo(message)

    click.echo()
    click.echo(
        f"Zeichen: {len(message)}/{max_length}"
    )

    image_url = event.image_url

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


def wait_for_media(
    client: httpx.Client,
    media_id: str,
    *, config: MastodonConfig | None = None,
) -> None:
    config = config or load_config()
    url = (
        f"{config.base_url}"
        f"/api/v1/media/{media_id}"
    )

    for _ in range(10):
        response = safe_get(client,
            url,
            headers={
                "Authorization": (
                    f"Bearer "
                    f"{config.access_token}"
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
    event: ContentItem | RenderedPost,
    *, config: MastodonConfig | None = None,
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
        f"{config.base_url}"
        "/api/v2/media"
    )

    begin_remote_mutation("mastodon_media")
    response = client.post(
        url,
        headers={
            "Authorization": (
                f"Bearer "
                f"{config.access_token}"
            ),
        },
        data={
            "description": (
                get_image_alt_text(event)
            ),
        },
        follow_redirects=False,
        files={
            "file": (
                filename,
                image_bytes,
                content_type,
            ),
        },
    )

    payload = response_payload(response, "Mastodon", config.access_token)

    media_id = payload.get("id")

    if not media_id:
        raise RuntimeError(
            "Mastodon hat keine "
            "Media-ID zurückgegeben: "
            + redact(str(payload), config.access_token)
        )

    return remote_identifier(media_id, "Mastodon", config.access_token)


def publish_mastodon_status(
    client: httpx.Client,
    event: ContentItem | RenderedPost,
    *,
    message: str | None = None,
    config: MastodonConfig | None = None,
) -> tuple[str, str | None]:
    config = config or load_config()
    if message is None:
        message = event.text if isinstance(event, RenderedPost) else build_mastodon_message(event)
    media_id = None

    if event.image_url:
        media_id = upload_mastodon_media(client, event, config=config)
        wait_for_media(client, media_id, config=config)

    data = {
        "status": message,
        "visibility": "public",
    }

    if media_id:
        data["media_ids[]"] = media_id

    begin_remote_mutation("mastodon_status")
    response = client.post(
        f"{config.base_url}/api/v1/statuses",
        headers={
            "Authorization": f"Bearer {config.access_token}",
        },
        data=data,
        follow_redirects=False,
    )

    payload = response_payload(response, "Mastodon", config.access_token)
    status_id = payload.get("id")

    if not status_id:
        raise RuntimeError(
            "Mastodon hat keine Status-ID zurückgegeben: "
            + redact(str(payload), config.access_token)
        )

    return (remote_identifier(status_id, "Mastodon", config.access_token),
            remote_url(payload.get("url"), config.access_token))


def publish_event(
    client: httpx.Client,
    conn: sqlite3.Connection,
    event: ContentItem,
    dry_run: bool,
    *,
    max_length: int = DEFAULT_STATUS_LIMIT,
    config: MastodonConfig | None = None,
    allow_repeat: bool = False,
) -> bool:
    post = render_post(event, 'mastodon', max_length=max_length)
    message = post.text
    print_event_preview(event, message, max_length)

    if dry_run:
        click.secho(
            "DRY RUN: kein Mastodon-Post veröffentlicht.",
            fg="yellow",
        )

        return False

    if not click.confirm(
        "Diesen Inhalt jetzt auf Mastodon veröffentlichen?",
        default=False,
    ):
        click.echo(
            "Übersprungen."
        )

        return False

    config = config or load_config()
    mastodon_status_id, mastodon_status_url = execute_publication(
        conn, "mastodon", event,
        lambda: publish_mastodon_status(client, post, message=message, config=config),
        lambda remote_id, remote_url: remember_post(conn, event, remote_id, remote_url, commit=False), allow_repeat=allow_repeat,
        message=message, target_ref=config.base_url,
    )
    click.secho(f"Mastodon-Post erstellt: {mastodon_status_id}", fg="green")
    click.echo(f"Gespeichert: {storage.item_key(event)} -> {mastodon_status_id}")
    if mastodon_status_url:
        click.echo(mastodon_status_url)

    return True


@click.command("mastodon", help="Inhalte für Mastodon auswählen, prüfen und veröffentlichen.")
@click.option("--source", default=DEFAULT_SOURCE, show_default=True, help="Konfigurierte JSON-Quelle.")
@click.option("--item-id", default=None, help="Quellenneutrale ID für die direkte Auswahl.")
@credential_options("Mastodon")
@click.option("--check-auth", "check_auth_only", is_flag=True, help="Nur Zugang und Zielkonto prüfen; hat Vorrang vor Auswahl und Veröffentlichung.")
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
        "Maximale Anzahl Einträge in der Auswahl. "
        "0 zeigt alle."
    ),
)
@click.option(
    "--include-published",
    is_flag=True,
    help=(
        "Auch bereits veröffentlichte Inhalte "
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
    help="Kulturbytes-Kompatibilität: Event-UUID; benötigt --date-identifier.",
)
@click.option(
    "--date-identifier",
    type=str,
    default=None,
    help="Kulturbytes-Kompatibilität: Termin-Slug oder Termin-UUID; benötigt --event-uuid.",
)
def mastodon_command(
    check_auth_only: bool,
    dry_run: bool,
    limit: int,
    include_published: bool,
    city: str | None,
    event_uuid: str | None,
    date_identifier: str | None, source: str = DEFAULT_SOURCE, item_id: str | None = None) -> None:
    if check_auth_only:
        check_auth(load_config())
        return
    config = load_config() if not dry_run else None
    base_url = config.base_url if config else load_base_url()
    status_limit: int | None = None

    def publish_with_instance_limit(
        client: httpx.Client, conn: sqlite3.Connection, event: ContentItem, dry_run: bool,
    ) -> bool:
        nonlocal status_limit
        if status_limit is None:
            status_limit = get_status_limit(client, base_url)
        return publish_event(client, conn, event, dry_run=dry_run, max_length=status_limit, config=config, allow_repeat=include_published)

    adapter, target = prepare_source(source, legacy_selector=(event_uuid, date_identifier), item_id=item_id)
    run_publisher(
        conn=init_database(),
        publish_item=publish_with_instance_limit,
        user_agent="Kulturbytes-Mastodon-Publisher/1.0",
        dry_run=dry_run,
        limit=limit,
        include_published=include_published,
        city=city,
        adapter=adapter, target=target,
    )
