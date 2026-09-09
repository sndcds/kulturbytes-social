"""The only adapter that knows Kulturbytes discovery/detail field names."""

from typing import TYPE_CHECKING

import httpx
from pydantic import ValidationError

from kulturbytes_common.sources.kulturbytes_api import (
    build_address,
    build_hashtags,
    format_price,
    get_event_details,
    get_event_url,
    get_events,
)

from .errors import SourceNotFound, SourceValidationError
from .kulturbytes_media import get_image_url
from .models import ContentItem, PublicationIdentity, SourceContext

if TYPE_CHECKING:
    from .loader import SourceDefinition


def bundled_definition() -> "SourceDefinition":
    from pathlib import Path

    from .loader import load_definition

    return load_definition(
        Path(__file__).resolve().parents[1] / "data/sources/kulturbytes.yaml"
    )


def context_for(definition, date_id: str, parent: str, revision: str) -> SourceContext:
    # Preserve the bundled source's existing journal keys; aliases have their own namespace.
    key = (
        date_id if definition.name == "kulturbytes" else f"{definition.name}:{date_id}"
    )
    return SourceContext(
        definition.name, PublicationIdentity(key, parent, revision), definition.media
    )


def from_kulturbytes(
    event: dict, definition: "SourceDefinition | None" = None
) -> ContentItem:
    definition = definition or bundled_definition()
    detail = event["date"]
    image = (event.get("images") or {}).get("main") or {}
    try:
        item = ContentItem(
            id=detail["uuid"],
            title=event["title"],
            subtitle=event.get("subtitle"),
            text=(event.get("summary") or event.get("description") or "").strip(),
            city=detail.get("venue_city"),
            location=detail.get("venue_name"),
            address=build_address(event),
            date=detail["start_date"],
            time=(detail.get("start_time") or "00:00")[:5],
            end_date=detail.get("end_date"),
            image_url=get_image_url(event) or None,
            image_alt=(
                image.get("alt") or f"Veranstaltungsbild zu {event['title']}"
            ).strip(),
            image_name=image.get("uuid") or detail["uuid"],
            link=get_event_url(event),
            tags=[tag.removeprefix("#") for tag in build_hashtags(event).split()],
            organizer=event.get("org_name"),
            price=format_price(event),
            ticket_link=detail.get("ticket_link") or None,
        )
    except (ValidationError, ValueError, TypeError, KeyError):
        raise SourceValidationError(
            "Quelle kulturbytes: ungültige kanonische Detaildaten."
        ) from None
    item._source_context = context_for(
        definition, detail["uuid"], event["uuid"], detail["slug"]
    )
    return item


class KulturbytesSourceAdapter:
    def __init__(self, definition: "SourceDefinition | None" = None) -> None:
        self.definition = definition or bundled_definition()
        self.name = self.definition.name
        self.behavior = self.definition.behavior
        self.summaries: dict[int, dict] = {}

    def resolve_legacy_selector(self, selector: tuple[str | None, str | None]):
        import click

        parent, date = selector
        if (parent is None) != (date is None):
            raise click.UsageError(
                "--event-uuid und --date-identifier müssen gemeinsam angegeben werden."
            )
        return (parent, date) if parent is not None else None

    def list_items(
        self, client: httpx.Client, *, target: str | tuple[str, str] | None = None
    ) -> list[ContentItem]:
        events = get_events(
            client, target=target if isinstance(target, tuple) else None
        )
        if target is not None:
            if isinstance(target, tuple):
                events = [
                    event
                    for event in events
                    if event["uuid"] == target[0]
                    and target[1] in (event["date_uuid"], event["date_slug"])
                ]
            else:
                events = [event for event in events if event["date_uuid"] == target]
            if len(events) != 1:
                raise SourceNotFound(
                    "Die Kombination aus Event-UUID und Terminkennung wurde in /api/events nicht eindeutig gefunden."
                )
        items = []
        for event in events:
            if event["release_status"] != "released":
                continue
            try:
                item = ContentItem(
                    id=event["date_uuid"],
                    title=event["title"],
                    date=event["start_date"],
                    time=event.get("start_time") or None,
                    city=event.get("venue_city"),
                    location=event.get("venue_name"),
                )
            except ValidationError:
                raise SourceValidationError(
                    "Quelle kulturbytes: ungültige kanonische Listendaten."
                ) from None
            item._source_context = context_for(
                self.definition, item.id, event["uuid"], event["date_slug"]
            )
            self.summaries[id(item)] = event
            items.append(item)
        return items

    def get_item(self, client: httpx.Client, item: ContentItem) -> ContentItem:
        summary = self.summaries[id(item)]
        event = get_event_details(client, summary)
        if (
            event["uuid"] != summary["uuid"]
            or event["date"]["uuid"] != item.id
            or event["date"]["slug"] != summary["date_slug"]
        ):
            raise SourceValidationError(
                f"Terminkonsistenzfehler: Event-UUID={summary['uuid']}, "
                f"date_slug={summary['date_slug']}, date_uuid={item.id}; "
                f"Detail-date_uuid={event['date']['uuid']}. Veröffentlichung abgebrochen."
            )
        return from_kulturbytes(
            {**event, "summary": (summary.get("summary") or "").strip()},
            self.definition,
        )
