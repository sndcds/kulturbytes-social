from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from kulturbytes_common.errors import NotFound, PublicationConflict
from kulturbytes_social.db.models import Job, record, now
from kulturbytes_social.db.session import transaction


class JobRepository:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def create(self, payload: dict) -> dict:
        with transaction(self.factory) as session:
            job = Job(platform=payload['platform'], payload=payload)
            session.add(job)
            session.flush()
            return record(job)

    def update(self, job_id: UUID, state: str, *, result: dict | None = None,
               error_class: str | None = None, error_message: str | None = None) -> dict:
        with transaction(self.factory) as session:
            row = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if row is None:
                raise NotFound()
            expected = ('queued',) if state in ('running', 'cancelled') else ('running',)
            if row.state not in expected:
                raise PublicationConflict('Job-Zustand erlaubt diesen Übergang nicht.')
            row.state, row.result, row.error_class, row.error_message = state, result, error_class, error_message
            if state == 'running':
                row.started_at = now()
            else:
                row.finished_at = now()
            session.flush()
            return record(row)

    def get(self, job_id: UUID) -> dict:
        with transaction(self.factory) as session:
            row = session.get(Job, job_id)
            if row is None:
                raise NotFound()
            return record(row)

    def list(self, *, state: str | None = None, limit: int = 50) -> list[dict]:
        query = select(Job).order_by(Job.created_at.desc(), Job.id.desc())
        if state:
            query = query.where(Job.state == state)
        if limit:
            query = query.limit(limit)
        with transaction(self.factory) as session:
            return [record(row) for row in session.scalars(query)]
