"""Selection and state checks over canonical items, independent of JSON properties."""

import sqlite3
from collections.abc import Callable
from datetime import date

import click
import httpx

from .selection import parse_selection
from .sources import SourceAdapter
from .sources.models import ContentItem
from .storage import already_published, item_key, unresolved_message
from .timezone import application_today


def select_items(items: list[ContentItem]) -> list[ContentItem]:
    click.echo()
    click.secho("Verfügbare Inhalte", bold=True)
    click.echo()
    for index, item in enumerate(items, 1):
        day = date.fromisoformat(item.date).strftime("%d.%m.%Y") if item.date else ""
        timestamp = " ".join(value for value in (day, (item.time or "")[:5]) if value)
        label = (timestamp + " — " if timestamp else "") + item.title
        if item.location:
            label += f" — {item.location}"
        if item.city:
            label += f" ({item.city})"
        click.echo(f"[{index:>3}] {label}")
    click.echo("\nAuswahl: 2 · 1,4,7 · 3-6 · 1,3-5,9 · all/alle/*; leer beendet.\n")
    value = click.prompt(
        "Welche Inhalte möchtest du auswählen?", default="", show_default=False
    )
    return [items[index] for index in parse_selection(value, len(items))]


def run_publisher(
    conn: sqlite3.Connection,
    publish_item: Callable[..., bool],
    user_agent: str,
    *,
    dry_run: bool,
    limit: int,
    include_published: bool,
    city: str | None,
    adapter: SourceAdapter,
    target=None,
) -> None:
    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=10, read=60, write=60, pool=10),
            follow_redirects=False,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        ) as client:
            items = adapter.list_items(client, target=target)
            click.echo(f"{len(items)} {adapter.name}-Einträge gefunden")
            candidates = []
            for item in sorted(
                items,
                key=lambda item: (item.date or "9999-12-31", item.time or "23:59"),
            ):
                if (
                    adapter.behavior.skip_past
                    and item.date
                    and item.date < application_today().isoformat()
                ):
                    continue
                if city and (item.city or "").casefold() != city.casefold():
                    continue
                key = item_key(item)
                active = unresolved_message(conn, key) if key else None
                if active:
                    if target is not None:
                        raise click.ClickException(active)
                    click.echo(active, err=True)
                    continue
                if key and not include_published and already_published(conn, key):
                    continue
                candidates.append(item)
            if limit > 0 and target is None:
                candidates = candidates[:limit]
            click.echo(f"{len(candidates)} Einträge stehen zur Auswahl.")
            if target is not None and not candidates:
                raise click.ClickException(
                    "Der gewählte Inhalt ist nicht verfügbar, durch Quellen-/Stadtfilter ausgeschlossen oder wurde bereits veröffentlicht (siehe --include-published)."
                )
            selected = (
                candidates
                if target is not None
                else select_items(candidates)
                if candidates
                else []
            )
            if not selected:
                click.echo("Keine Inhalte ausgewählt.")
                return
            click.secho(f"\n{len(selected)} Inhalt(e) ausgewählt.\n", bold=True)
            for item in selected:
                key = item_key(item)
                if key and include_published and already_published(conn, key):
                    click.echo(
                        "WARNUNG: Dieser Inhalt wurde bereits veröffentlicht: "
                        + item.title
                    )
                    if not click.confirm("Trotzdem fortfahren?", default=False):
                        continue
                try:
                    detail = adapter.get_item(client, item)
                    if (
                        adapter.behavior.skip_past
                        and detail.date
                        and detail.date < application_today().isoformat()
                    ) or (city and (detail.city or "").casefold() != city.casefold()):
                        raise click.ClickException(
                            "Detailinhalt durch Quellen-/Stadtfilter ausgeschlossen."
                        )
                    publish_item(client, conn, detail, dry_run=dry_run)
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
                    context = f"Quelle={adapter.name}, ID={item.id or 'ohne ID'}"
                    if target is not None:
                        raise click.ClickException(f"{message} {context}") from None
                    click.secho(
                        f"Fehler bei {item.title}: {message} {context}",
                        fg="red",
                        err=True,
                    )
    finally:
        conn.close()
