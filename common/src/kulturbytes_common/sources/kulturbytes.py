"""The only adapter that knows Kulturbytes discovery/detail field names."""

import httpx
from pydantic import ValidationError

from kulturbytes_common.events import (
    build_address,
    build_hashtags,
    format_price,
    get_event_details,
    get_event_url,
    get_events,
    should_publish,
)
from kulturbytes_common.media import get_image_url

from .errors import SourceNotFound, SourceValidationError
from .models import PublicationIdentity, SocialItem


def from_kulturbytes(event: dict) -> SocialItem:
    detail = event["date"]
    image = (event.get("images") or {}).get("main") or {}
    try:
        item = SocialItem(
            id=detail["uuid"],
            title=event["title"],
            subtitle=event.get("subtitle"),
            text=(event.get("summary") or event.get("description") or "").strip(),
            city=detail.get("venue_city"),
            venue=detail.get("venue_name"),
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
    item._origin = PublicationIdentity(
        "kulturbytes", detail["uuid"], event["uuid"], detail["slug"]
    )
    return item


class KulturbytesSourceAdapter:
    name = "kulturbytes"

    def __init__(self) -> None:
        self.summaries: dict[int, dict] = {}

    def list_items(
        self, client: httpx.Client, *, target: str | tuple[str, str] | None = None
    ) -> list[SocialItem]:
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
            if not should_publish(event):
                continue
            try:
                item = SocialItem(
                    id=event["date_uuid"],
                    title=event["title"],
                    date=event["start_date"],
                    time=event.get("start_time") or None,
                    city=event.get("venue_city"),
                    venue=event.get("venue_name"),
                )
            except ValidationError:
                raise SourceValidationError(
                    "Quelle kulturbytes: ungültige kanonische Listendaten."
                ) from None
            item._origin = PublicationIdentity(
                self.name, item.id, event["uuid"], event["date_slug"]
            )
            self.summaries[id(item)] = event
            items.append(item)
        return items

    def get_item(self, client: httpx.Client, item: SocialItem) -> SocialItem:
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
            {**event, "summary": (summary.get("summary") or "").strip()}
        )
