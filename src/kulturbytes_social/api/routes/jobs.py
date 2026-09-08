from uuid import UUID
from fastapi import APIRouter, Depends, Query
from kulturbytes_social.api.dependencies import jobs
from kulturbytes_social.api.schemas import PublishRequest, JobResponse, JobState
router = APIRouter(tags=['Jobs'])


@router.post('/jobs', response_model=JobResponse, status_code=201)
def create_job(body: PublishRequest, service=Depends(jobs)):
    return service.execute(body.model_dump())


@router.get('/jobs', response_model=list[JobResponse])
def list_jobs(state: JobState | None = None, limit: int = Query(50, ge=0, le=1000), service=Depends(jobs)):
    return service.repository.list(state=state.value if state else None, limit=limit)


@router.get('/jobs/{job_id}', response_model=JobResponse)
def get_job(job_id: UUID, service=Depends(jobs)):
    return service.repository.get(job_id)


@router.post('/jobs/{job_id}/cancel', response_model=JobResponse)
def cancel(job_id: UUID, service=Depends(jobs)):
    return service.repository.update(job_id, 'cancelled')
