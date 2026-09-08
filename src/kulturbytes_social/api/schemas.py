from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from kulturbytes_common.models import Identifier
from kulturbytes_social.db.models import AttemptState, JobState


class Platform(StrEnum):
    facebook = 'facebook'
    instagram = 'instagram'
    mastodon = 'mastodon'


class RequestModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class PreviewRequest(RequestModel):
    platform: Literal['facebook', 'instagram', 'mastodon']
    event_uuid: Identifier
    date_identifier: Identifier
    force_repeat: bool = False
    city: Annotated[str, Field(max_length=200)] | None = None


class PublishRequest(PreviewRequest):
    expected_content_sha256: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')] | None = None


class ResolveRequest(RequestModel):
    outcome: Literal['published', 'failed', 'cancelled']
    remote_id: Annotated[str, Field(max_length=200)] | None = None
    remote_url: Annotated[str, Field(max_length=2000)] | None = None
    confirmed: Literal[True]  # Operator asserts worker stopped and platform inspected.


class AttemptResponse(BaseModel):
    id: UUID
    platform: Platform
    event_uuid: str
    date_uuid: str
    date_slug: str
    state: AttemptState
    mutation_stage: str | None
    target_ref: str | None
    content_sha256: str
    remote_id: str | None
    remote_url: str | None
    error_class: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class PublicationResponse(BaseModel):
    id: UUID
    attempt_id: UUID
    platform: Platform
    event_uuid: str
    date_uuid: str
    date_slug: str
    remote_id: str
    remote_url: str | None
    published_at: datetime
    created_at: datetime
    updated_at: datetime


class JobResponse(BaseModel):
    id: UUID
    job_type: str
    platform: Platform | None
    state: JobState
    payload: dict
    result: dict | None
    error_class: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class PreviewResponse(BaseModel):
    text: str
    image_url: str | None
    event: dict
    published: bool
    content_sha256: str


class PublishResponse(BaseModel):
    attempt_id: UUID
    publication_id: UUID
    state: Literal['published']
    remote_id: str
    remote_url: str | None


class EventDetailResponse(BaseModel):
    event: dict
    summary: dict
