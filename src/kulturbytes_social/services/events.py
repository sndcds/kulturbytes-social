import click
import httpx
from kulturbytes_social.db.repositories.publications import PublicationRepository
from kulturbytes_common.events import get_events, get_event_details, should_publish
from kulturbytes_common.errors import InvalidEvent, NotFound, PublicationConflict, AlreadyPublished


class EventService:
    def __init__(self, repository: PublicationRepository, client: httpx.Client) -> None:
        self.repository, self.client = repository, client

    def discover(self, *, platform: str, city: str | None = None, include_published: bool = False,
                 limit: int = 50, target: tuple[str, str] | None = None) -> list[dict]:
        try:
            events = get_events(self.client, target=target)
        except (click.ClickException, httpx.HTTPError):
            raise InvalidEvent('Kulturbytes-Antwort ist ungültig oder nicht erreichbar.') from None
        if target:
            matches = [event for event in events if event['uuid'] == target[0]
                       and target[1] in (event['date_uuid'], event['date_slug'])]
            if not matches:
                raise NotFound('Termin nicht gefunden.')
            if len(matches) != 1:
                raise InvalidEvent()
            events = matches
        published, active = self.repository.known_dates(platform)
        result = []
        for event in events:
            if not should_publish(event) or (city and (event.get('venue_city') or '').casefold() != city.casefold()):
                continue
            if event['date_uuid'] in active:
                if target:
                    raise PublicationConflict()
                continue
            if event['date_uuid'] in published and not include_published:
                if target:
                    raise AlreadyPublished()
                continue
            result.append({**event, 'published': event['date_uuid'] in published})
        result.sort(key=lambda event: (event['start_date'], event.get('start_time') or '23:59'))
        if target and not result:
            raise InvalidEvent()
        return result[:limit] if limit else result

    def detail(self, event_uuid: str, date_identifier: str, **filters) -> tuple[dict, dict]:
        summary = self.discover(target=(event_uuid, date_identifier), limit=0, **filters)[0]
        try:
            detail = get_event_details(self.client, summary)
        except (click.ClickException, httpx.HTTPError):
            raise InvalidEvent('Ungültige Detailantwort.') from None
        if (detail['uuid'] != summary['uuid'] or detail['date']['uuid'] != summary['date_uuid']
                or detail['date']['slug'] != summary['date_slug']):
            raise InvalidEvent('Event-UUID, Termin-UUID oder Slug stimmen nicht überein.')
        return {**detail, 'summary': (summary.get('summary') or '').strip()}, summary
