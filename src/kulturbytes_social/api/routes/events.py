from fastapi import APIRouter, Depends, Query
from kulturbytes_social.api.dependencies import publications
from kulturbytes_social.api.schemas import Platform, EventDetailResponse
router = APIRouter(tags=['Events'])


@router.get('/events')
def events(platform: Platform, city: str | None = None, limit: int = Query(50, ge=0, le=1000),
           include_published: bool = False, service=Depends(publications)):
    return service.events.discover(platform=platform.value, city=city, limit=limit, include_published=include_published)


@router.get('/events/{event_uuid}/dates/{date_identifier}', response_model=EventDetailResponse)
def detail(event_uuid: str, date_identifier: str, platform: Platform, city: str | None = None,
           include_published: bool = False, service=Depends(publications)):
    event, summary = service.events.detail(event_uuid, date_identifier, platform=platform.value,
                                         city=city, include_published=include_published)
    return {'event': event, 'summary': summary}
