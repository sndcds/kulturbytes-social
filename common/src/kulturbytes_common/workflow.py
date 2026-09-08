from collections.abc import Callable
import sqlite3

import click
import httpx

from .database import already_published
from .events import get_events, get_event_details, should_publish
from .selection import select_events


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
) -> None:
    timeout = httpx.Timeout(
        connect=10.0,
        read=60.0,
        write=60.0,
        pool=10.0,
    )

    headers = {
        "User-Agent": user_agent,
        "Accept": (
            "application/json"
        ),
    }

    try:
        if (event_uuid is None) != (date_identifier is None):
            raise click.UsageError(
                "--event-uuid und --date-identifier müssen gemeinsam angegeben werden."
            )
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            events = get_events(client, target=(event_uuid, date_identifier) if event_uuid is not None else None)

            click.echo(
                f"{len(events)} "
                "Kulturbytes-Termine gefunden"
            )

            if event_uuid is not None:
                events = [
                    event for event in events
                    if event.get("uuid") == event_uuid
                    and date_identifier in (
                        event.get("date_slug"), event.get("date_uuid"),
                    )
                ]
                if len(events) != 1:
                    raise click.ClickException(
                        "Die Kombination aus Event-UUID und Terminkennung wurde "
                        "in /api/events nicht eindeutig gefunden."
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

            candidates: list[dict] = []

            for summary_event in events:
                if not should_publish(
                    summary_event
                ):
                    continue

                date_uuid = summary_event.get(
                    "date_uuid"
                )

                if not date_uuid:
                    continue

                if (
                    not include_published
                    and already_published(
                        conn,
                        date_uuid,
                    )
                ):
                    continue

                if city:
                    venue_city = (
                        summary_event.get(
                            "venue_city",
                            "",
                        )
                    )

                    if (
                        (venue_city or "").casefold()
                        != city.casefold()
                    ):
                        continue

                candidates.append(
                    summary_event
                )

            if limit > 0:
                candidates = (
                    candidates[:limit]
                )

            click.echo(
                f"{len(candidates)} "
                "Termine stehen zur Auswahl."
            )

            if event_uuid is not None:
                if not candidates:
                    raise click.ClickException(
                        "Der gewählte Termin ist nicht freigegeben, liegt in der "
                        "Vergangenheit, passt nicht zum Stadtfilter oder wurde bereits "
                        "veröffentlicht (siehe --include-published)."
                    )
                selected_events = candidates
            else:
                selected_events = select_events(candidates)

            if not selected_events:
                click.echo(
                    "Keine Events ausgewählt."
                )
                return

            click.echo()
            click.secho(
                (
                    f"{len(selected_events)} "
                    "Event(s) ausgewählt."
                ),
                bold=True,
            )

            click.echo()

            for summary_event in selected_events:
                date_uuid = (
                    summary_event[
                        "date_uuid"
                    ]
                )

                if (
                    include_published
                    and already_published(
                        conn,
                        date_uuid,
                    )
                ):
                    click.secho(
                        (
                            "WARNUNG: Dieser Termin "
                            "wurde bereits veröffentlicht:"
                        ),
                        fg="yellow",
                    )

                    click.echo(
                        summary_event["title"]
                    )

                    if not click.confirm(
                        "Trotzdem fortfahren?",
                        default=False,
                    ):
                        continue

                try:
                    click.echo()
                    click.echo(
                        "Lade Detaildaten:"
                    )

                    click.echo(
                        (
                            f"  UUID: "
                            f"{summary_event['uuid']}"
                        )
                    )

                    click.echo(
                        (
                            f"  Termin: "
                            f"{summary_event['date_slug']}"
                        )
                    )

                    event = get_event_details(
                        client,
                        summary_event,
                    )
                    # Use the list summary for social text, while keeping all
                    # other metadata from the detailed event response.
                    event = {
                        **event,
                        "summary": (summary_event.get("summary") or "").strip(),
                    }

                    detailed_date = event.get("date")
                    detailed_date_uuid = (
                        detailed_date.get("uuid")
                        if isinstance(detailed_date, dict)
                        else None
                    )

                    if (not detailed_date_uuid or detailed_date_uuid != date_uuid
                            or event["uuid"] != summary_event["uuid"] or event["date"]["slug"] != summary_event["date_slug"]):
                        raise click.ClickException(
                            "Terminkonsistenzfehler: "
                            f"Event-UUID={summary_event['uuid']}, "
                            f"date_slug={summary_event['date_slug']}. "
                            f"/api/events liefert date_uuid={date_uuid}, "
                            "die Detailantwort liefert "
                            f"date_uuid={detailed_date_uuid!r} "
                            "(fehlend oder abweichend). "
                            "Veröffentlichung wurde für diesen Termin abgebrochen."
                        )

                    publish_event(
                        client,
                        conn,
                        event,
                        dry_run=dry_run,
                    )

                except httpx.HTTPStatusError as exc:
                    if event_uuid is not None:
                        raise click.ClickException(str(exc)) from exc
                    click.secho(
                        (
                            "\nHTTP/API-Fehler bei: "
                            f"{summary_event.get('title')}"
                        ),
                        fg="red",
                        err=True,
                    )

                    click.echo(
                        str(exc),
                        err=True,
                    )

                except Exception as exc:
                    if event_uuid is not None:
                        raise click.ClickException(str(exc)) from exc
                    click.secho(
                        (
                            "\nFehler bei: "
                            f"{summary_event.get('title')}"
                        ),
                        fg="red",
                        err=True,
                    )

                    click.echo(
                        (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        ),
                        err=True,
                    )

    finally:
        conn.close()
