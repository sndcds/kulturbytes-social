"""Bluesky command delegates source selection and durable publishing to the core."""

import sqlite3
from functools import partial

import click
import httpx

from kulturbytes_common import storage
from kulturbytes_common.credentials import credential_options
from kulturbytes_common.publications import execute_publication
from kulturbytes_common.rendering import render_post
from kulturbytes_common.sources.cli import DEFAULT_SOURCE, prepare_source
from kulturbytes_common.sources.models import ContentItem
from kulturbytes_common.text_limits import grapheme_count
from kulturbytes_common.workflow import run_publisher

from .auth import Session, authenticate, load_config
from .publishing import publish_post

DATABASE_PATH = None
remember_post = partial(storage.remember_post, platform="bluesky")


def init_database() -> sqlite3.Connection:
    return storage.init_database("bluesky", DATABASE_PATH)


def publish_event(
    client: httpx.Client,
    conn: sqlite3.Connection,
    event: ContentItem,
    dry_run: bool,
    *,
    session: Session | None = None,
    allow_repeat: bool = False,
) -> bool:
    post = render_post(event, "bluesky")
    click.echo(post.text)
    click.echo(
        f"Grapheme: {grapheme_count(post.text)}/300 · UTF-8-Bytes: {len(post.text.encode('utf-8'))}/3000"
    )
    if post.image_url:
        click.echo(f"🖼 {post.image_url}")
        click.echo(f"Alt-Text: {post.image_alt}")
    if dry_run:
        click.echo("DRY RUN: kein Bluesky-Post veröffentlicht.")
        return False
    if session is None:
        raise click.ClickException("Bluesky: authentifizierte Session fehlt.")
    if not click.confirm(
        "Diesen Inhalt jetzt auf Bluesky veröffentlichen?", default=False
    ):
        return False
    uri, url = execute_publication(
        conn,
        "bluesky",
        event,
        lambda: publish_post(client, session, post),
        lambda remote_id, remote_url: remember_post(
            conn, event, remote_id, remote_url, commit=False
        ),
        allow_repeat=allow_repeat,
        message=post.text,
        target_ref=session.did,
    )
    click.echo(f"Bluesky-Post erstellt: {uri}")
    click.echo(url)
    return True


@click.command(
    "bluesky", help="Inhalte für Bluesky auswählen, prüfen und veröffentlichen."
)
@click.option("--source", default=DEFAULT_SOURCE, show_default=True)
@click.option("--item-id", default=None)
@credential_options("Bluesky")
@click.option(
    "--check-auth",
    "check_auth_only",
    is_flag=True,
    help="Nur App-Password-Session und Konto prüfen.",
)
@click.option(
    "--dry-run/--publish",
    default=True,
    help="Vorschau oder nach Bestätigung veröffentlichen.",
)
@click.option("--limit", type=click.IntRange(min=0), default=50, show_default=True)
@click.option("--include-published", is_flag=True)
@click.option("--city", default=None)
@click.option(
    "--event-uuid", default=None, help="Legacy-Auswahl; benötigt --date-identifier."
)
@click.option("--date-identifier", default=None)
def bluesky_command(
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
    config = load_config() if check_auth_only or not dry_run else None
    # Separate from the workflow/source client; never inherit proxies or auth state.
    with httpx.Client(
        trust_env=False, follow_redirects=False, timeout=httpx.Timeout(60, connect=10)
    ) as client:
        session = authenticate(client, config) if config else None
        if check_auth_only:
            click.echo("✓ Bluesky App Password gültig")
            click.echo(f"✓ Konto: {session.handle} ({session.did})")
            return
        adapter, target = prepare_source(
            source, legacy_selector=(event_uuid, date_identifier), item_id=item_id
        )

        def publish_selected(_source_client, conn, event, dry_run):
            return publish_event(
                client,
                conn,
                event,
                dry_run,
                session=session,
                allow_repeat=include_published,
            )

        run_publisher(
            conn=init_database(),
            publish_item=publish_selected,
            user_agent="Content-Bluesky-Publisher/1.0",
            dry_run=dry_run,
            limit=limit,
            include_published=include_published,
            city=city,
            adapter=adapter,
            target=target,
        )
