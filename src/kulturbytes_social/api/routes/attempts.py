from uuid import UUID
from fastapi import APIRouter, Depends, Query
from kulturbytes_social.api.dependencies import repository, publications
from kulturbytes_social.api.schemas import Platform, AttemptState, AttemptResponse, ResolveRequest
router = APIRouter(tags=['Attempts'])


@router.get('/publication-attempts', response_model=list[AttemptResponse])
def attempts(platform: Platform | None = None, state: AttemptState | None = None, active: bool = False,
             date_uuid: str | None = None, limit: int = Query(50, ge=0, le=1000), repo=Depends(repository)):
    return repo.attempts(platform=platform.value if platform else None, state=state.value if state else None,
                         active=active, date_uuid=date_uuid, limit=limit)


@router.get('/publication-attempts/{attempt_id}', response_model=AttemptResponse)
def attempt(attempt_id: UUID, repo=Depends(repository)):
    return repo.attempt(attempt_id)


@router.post('/publication-attempts/{attempt_id}/resolve')
def resolve(attempt_id: UUID, body: ResolveRequest, service=Depends(publications)):
    return service.resolve(attempt_id, outcome=body.outcome, remote_id=body.remote_id, remote_url_value=body.remote_url)
