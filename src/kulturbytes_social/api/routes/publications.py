from uuid import UUID
from fastapi import APIRouter, Depends, Query
from kulturbytes_social.api.dependencies import publications, repository
from kulturbytes_social.api.schemas import PublishRequest, PreviewRequest, PublicationResponse, Platform, PreviewResponse, PublishResponse
router = APIRouter(tags=['Publications'])


@router.post('/publications/preview', response_model=PreviewResponse, summary='Preview without reserving or publishing')
def preview(body: PreviewRequest, service=Depends(publications)):
    return service.preview(**body.model_dump())


@router.post('/publications', status_code=201, response_model=PublishResponse, summary='Publish one event date synchronously')
def publish(body: PublishRequest, service=Depends(publications)):
    return service.publish(**body.model_dump())


@router.get('/publications', response_model=list[PublicationResponse])
def history(platform: Platform | None = None, date_uuid: str | None = None,
            limit: int = Query(50, ge=0, le=1000), repo=Depends(repository)):
    return repo.publications(platform=platform.value if platform else None, date_uuid=date_uuid, limit=limit)


@router.get('/publications/{publication_id}', response_model=PublicationResponse)
def publication(publication_id: UUID, repo=Depends(repository)):
    return repo.publication(publication_id)
