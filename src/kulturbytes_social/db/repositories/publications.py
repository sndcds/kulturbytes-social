"""Short PostgreSQL transactions; no platform calls or UI dependencies."""
import hashlib
from uuid import UUID
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, Session
from kulturbytes_common.errors import AlreadyPublished, DatabaseUnavailable, NotFound, PublicationConflict
from kulturbytes_social.db.models import ACTIVE, Attempt, Publication, record, now
from kulturbytes_social.db.session import transaction


def lock_date(session: Session, platform: str, date_uuid: str) -> None:
    key = int.from_bytes(hashlib.sha256(f'{platform}:{date_uuid}'.encode()).digest()[:8], signed=True)
    session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})


class PublicationRepository:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def readiness(self) -> None:
        with transaction(self.factory) as session:
            session.execute(select(Attempt.id).limit(1))
            session.execute(select(Publication.id).limit(1))
            session.execute(text('SELECT id FROM jobs LIMIT 1'))

    def known_dates(self, platform: str) -> tuple[set[str], set[str]]:
        with transaction(self.factory) as session:
            published = set(session.scalars(select(Publication.date_uuid).where(Publication.platform == platform)))
            active = set(session.scalars(select(Attempt.date_uuid).where(Attempt.platform == platform, Attempt.state.in_(ACTIVE))))
            return published, active

    def reserve(self, *, platform: str, event: dict, target_ref: str, fingerprint: str, force_repeat: bool) -> dict:
        try:
            with transaction(self.factory) as session:
                lock_date(session, platform, event['date']['uuid'])
                active = session.scalar(select(Attempt.id).where(Attempt.platform == platform,
                    Attempt.date_uuid == event['date']['uuid'], Attempt.state.in_(ACTIVE)))
                if active:
                    raise PublicationConflict(attempt_id=str(active))
                if not force_repeat and session.scalar(select(Publication.id).where(
                        Publication.platform == platform, Publication.date_uuid == event['date']['uuid']).limit(1)):
                    raise AlreadyPublished()
                attempt = Attempt(platform=platform, event_uuid=event['uuid'], date_uuid=event['date']['uuid'],
                                  date_slug=event['date']['slug'], target_ref=target_ref, content_sha256=fingerprint)
                session.add(attempt)
                session.flush()
                return record(attempt)
        except DatabaseUnavailable as exc:
            # transaction() deliberately hides the driver message; unique index remains final defense.
            if isinstance(exc.__context__, IntegrityError):
                raise PublicationConflict() from None
            raise

    def attempt(self, attempt_id: UUID) -> dict:
        with transaction(self.factory) as session:
            row = session.get(Attempt, attempt_id)
            if row is None:
                raise NotFound()
            return record(row)

    def attempts(self, *, platform: str | None = None, date_uuid: str | None = None,
                 state: str | None = None, active: bool = False, limit: int = 50) -> list[dict]:
        if active and state and state not in ACTIVE:
            raise PublicationConflict('Aktive Filter sind mit einem abgeschlossenen Zustand nicht kombinierbar.')
        query = select(Attempt).order_by(Attempt.created_at.desc(), Attempt.id.desc())
        for column, value in ((Attempt.platform, platform), (Attempt.date_uuid, date_uuid), (Attempt.state, state)):
            if value is not None:
                query = query.where(column == value)
        if active:
            query = query.where(Attempt.state.in_(ACTIVE))
        if limit:
            query = query.limit(limit)
        with transaction(self.factory) as session:
            return [record(row) for row in session.scalars(query)]

    def publications(self, *, platform: str | None = None, date_uuid: str | None = None, limit: int = 50) -> list[dict]:
        query = select(Publication).order_by(Publication.published_at.desc(), Publication.id.desc())
        if platform:
            query = query.where(Publication.platform == platform)
        if date_uuid:
            query = query.where(Publication.date_uuid == date_uuid)
        if limit:
            query = query.limit(limit)
        with transaction(self.factory) as session:
            return [record(row) for row in session.scalars(query)]

    def publication(self, publication_id: UUID) -> dict:
        with transaction(self.factory) as session:
            row = session.get(Publication, publication_id)
            if row is None:
                raise NotFound()
            return record(row)

    def transition(self, attempt_id: UUID, state: str, previous: tuple[str, ...], **values) -> dict:
        with transaction(self.factory) as session:
            row = session.scalar(select(Attempt).where(Attempt.id == attempt_id).with_for_update())
            if row is None:
                raise NotFound()
            if row.state not in previous:
                raise PublicationConflict('Der Versuch hat seinen Zustand geändert.')
            row.state, row.updated_at = state, now()
            for key, value in values.items():
                setattr(row, key, value)
            if state == 'publishing' and row.started_at is None:
                row.started_at = now()
            if state in ('published', 'failed', 'cancelled'):
                row.finished_at = now()
            session.flush()
            return record(row)

    def finalize(self, attempt_id: UUID, *, resolve_id: str | None = None, resolve_url: str | None = None) -> dict:
        with transaction(self.factory) as session:
            identity = session.get(Attempt, attempt_id)
            if identity is None:
                raise NotFound()
            lock_date(session, identity.platform, identity.date_uuid)
            row = session.scalar(select(Attempt).where(Attempt.id == attempt_id).with_for_update().execution_options(populate_existing=True))
            if row.state not in ACTIVE or (row.state != 'remote_succeeded' and not resolve_id):
                raise PublicationConflict('Versuch kann nicht finalisiert werden.')
            if row.remote_id and ((resolve_id and resolve_id != row.remote_id) or (resolve_url and resolve_url != row.remote_url)):
                raise PublicationConflict('Bestätigte Remote-Referenz darf nicht überschrieben werden.')
            row.remote_id = row.remote_id or resolve_id
            row.remote_url = row.remote_url or resolve_url
            publication = Publication(attempt_id=row.id, platform=row.platform, event_uuid=row.event_uuid,
                date_uuid=row.date_uuid, date_slug=row.date_slug, remote_id=row.remote_id, remote_url=row.remote_url)
            session.add(publication)
            row.state, row.updated_at, row.finished_at = 'published', now(), now()
            session.flush()
            return record(publication)
