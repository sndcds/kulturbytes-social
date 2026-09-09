"""Selection and state checks over canonical items, independent of JSON properties."""

import sqlite3
from collections.abc import Callable
from datetime import date

import click
import httpx

from .database import already_published
from .publications import describe_attempt, unresolved_attempt
from .selection import parse_selection
from .sources.loader import load_source
from .sources.models import SocialItem
from .storage import item_key
from .timezone import application_today


def select_items(items: list[SocialItem]) -> list[SocialItem]:
    click.echo()
    click.secho("Verfügbare Veranstaltungen", bold=True)
    click.echo()
    for index, item in enumerate(items, 1):
        day = date.fromisoformat(item.date).strftime("%d.%m.%Y") if item.date else ""
        label = f"{day} {(item.time or '')[:5]} — {item.title}"
        if item.venue:
            label += f" — {item.venue}"
        if item.city:
            label += f" ({item.city})"
        click.echo(f"[{index:>3}] {label}")
    click.echo("\nAuswahl: 2 · 1,4,7 · 3-6 · 1,3-5,9 · all/alle/*; leer beendet.\n")
    value = click.prompt(
        "Welche Events möchtest du auswählen?", default="", show_default=False
    )
    return [items[index] for index in parse_selection(value, len(items))]


def run_publisher(
    conn: sqlite3.Connection,
    publish_event: Callable[..., bool],
    user_agent: str,
    *,
    dry_run: bool,
    limit: int,
    include_published: bool,
    city: str | None,
    event_uuid: str | None = None,
    date_identifier: str | None = None,
    source: str = "kulturbytes",
    item_id: str | None = None,
) -> None:
    try:
        if (event_uuid is None) != (date_identifier is None):
            raise click.UsageError(
                "--event-uuid und --date-identifier müssen gemeinsam angegeben werden."
            )
        if (event_uuid is not None and source != "kulturbytes") or (
            event_uuid is not None and item_id is not None
        ):
            raise click.UsageError(
                "Generische Quellen verwenden --item-id; Kulturbytes-Flags sind nicht damit kombinierbar."
            )
        adapter = load_source(source)
        target = (event_uuid, date_identifier) if event_uuid is not None else item_id
        with httpx.Client(
            timeout=httpx.Timeout(connect=10, read=60, write=60, pool=10),
            follow_redirects=False,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        ) as client:
            items = adapter.list_items(client, target=target)
            click.echo(f"{len(items)} {source}-Einträge gefunden")
            candidates = []
            for item in sorted(
                items,
                key=lambda item: (item.date or "9999-12-31", item.time or "23:59"),
            ):
                if item.date and item.date < application_today().isoformat():
                    continue
                if city and (item.city or "").casefold() != city.casefold():
                    continue
                key = item_key(item)
                active = unresolved_attempt(conn, key) if key else None
                if active:
                    message = (
                        "Termin ist reserviert oder ungeklärt: "
                        + describe_attempt(active)
                    )
                    message += ". Mit kulturbytes-social attempts prüfen und auflösen."
                    if target is not None:
                        raise click.ClickException(message)
                    click.echo(message, err=True)
                    continue
                if key and not include_published and already_published(conn, key):
                    continue
                candidates.append(item)
            if limit > 0 and target is None:
                candidates = candidates[:limit]
            click.echo(f"{len(candidates)} Termine stehen zur Auswahl.")
            if target is not None and not candidates:
                raise click.ClickException(
                    "Der gewählte Termin ist nicht freigegeben, liegt in der Vergangenheit, passt nicht zum Stadtfilter oder wurde bereits veröffentlicht (siehe --include-published)."
                )
            selected = (
                candidates
                if target is not None
                else select_items(candidates)
                if candidates
                else []
            )
            if not selected:
                click.echo("Keine Events ausgewählt.")
                return
            click.secho(f"\n{len(selected)} Event(s) ausgewählt.\n", bold=True)
            for item in selected:
                key = item_key(item)
                if key and include_published and already_published(conn, key):
                    click.echo(
                        "WARNUNG: Dieser Termin wurde bereits veröffentlicht: "
                        + item.title
                    )
                    if not click.confirm("Trotzdem fortfahren?", default=False):
                        continue
                try:
                    detail = adapter.get_item(client, item)
                    publish_event(client, conn, detail, dry_run=dry_run)
                except Exception as exc:
                    if isinstance(exc, click.ClickException):
                        message = exc.format_message()
                    elif isinstance(exc, httpx.HTTPStatusError):
                        message = f"HTTP/API-Fehler (HTTP {exc.response.status_code})."
                    elif isinstance(exc, httpx.RequestError):
                        message = "HTTP/API-Netzwerkfehler."
                    else:
                        message = (
                            f"Veröffentlichung fehlgeschlagen ({type(exc).__name__})."
                        )
                    context = f"Quelle={source}, ID={item.id or 'ohne ID'}"
                    if target is not None:
                        raise click.ClickException(f"{message} {context}") from None
                    click.secho(
                        f"Fehler bei {item.title}: {message} {context}",
                        fg="red",
                        err=True,
                    )
    finally:
        conn.close()
