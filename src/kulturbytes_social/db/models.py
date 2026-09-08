"""PostgreSQL publication history. Schema changes are owned by Alembic."""
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(timezone.utc)


class AttemptState(StrEnum):
    reserved = 'reserved'
    publishing = 'publishing'
    remote_succeeded = 'remote_succeeded'
    published = 'published'
    failed = 'failed'
    cancelled = 'cancelled'


class JobState(StrEnum):
    queued = 'queued'
    running = 'running'
    succeeded = 'succeeded'
    failed = 'failed'
    cancelled = 'cancelled'


ACTIVE = ('reserved', 'publishing', 'remote_succeeded')
PLATFORMS = ('facebook', 'instagram', 'mastodon')


class Base(DeclarativeBase):
    pass


class Attempt(Base):
    __tablename__ = 'publication_attempts'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    platform: Mapped[str] = mapped_column(String(20))
    event_uuid: Mapped[str] = mapped_column(String(200))
    date_uuid: Mapped[str] = mapped_column(String(200))
    date_slug: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(30), default='reserved')
    mutation_stage: Mapped[str | None] = mapped_column(String(40))
    target_ref: Mapped[str | None] = mapped_column(String(200))
    content_sha256: Mapped[str] = mapped_column(String(64))
    remote_id: Mapped[str | None] = mapped_column(String(200))
    remote_url: Mapped[str | None] = mapped_column(Text)
    error_class: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("platform IN ('facebook','instagram','mastodon')", name='attempt_platform'),
        CheckConstraint("state IN ('reserved','publishing','remote_succeeded','published','failed','cancelled')", name='attempt_state'),
        CheckConstraint("mutation_stage IS NULL OR mutation_stage IN ('facebook_photo','facebook_feed','mastodon_media','mastodon_status','instagram_container','instagram_publish')", name='mutation_stage'),
        Index('active_publication', 'platform', 'date_uuid', unique=True,
              postgresql_where=text("state IN ('reserved','publishing','remote_succeeded')")),
        Index('attempt_filter', 'platform', 'state', 'created_at'),
        Index('attempt_date', 'date_uuid'),
    )


class Publication(Base):
    __tablename__ = 'publications'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey('publication_attempts.id'), unique=True)
    platform: Mapped[str] = mapped_column(String(20))
    event_uuid: Mapped[str] = mapped_column(String(200))
    date_uuid: Mapped[str] = mapped_column(String(200))
    date_slug: Mapped[str] = mapped_column(String(200))
    remote_id: Mapped[str] = mapped_column(String(200))
    remote_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (Index('publication_date', 'platform', 'date_uuid'), Index('publication_time', 'published_at'),)


class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_type: Mapped[str] = mapped_column(String(30), default='publication')
    platform: Mapped[str | None] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(30), default='queued')
    payload: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error_class: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("state IN ('queued','running','succeeded','failed','cancelled')", name='job_state'),
                      Index('job_filter', 'state', 'created_at'))


def record(model: Base) -> dict:
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}
