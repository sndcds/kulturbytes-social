"""Source-neutral content and an internal publication identity, never raw JSON."""

from dataclasses import dataclass
from datetime import date as calendar_date
from datetime import time as clock_time
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from ..network import MediaPolicy


@dataclass(frozen=True)
class PublicationIdentity:
    publication_key: str
    content_key: str
    revision: str


@dataclass(frozen=True)
class SourceContext:
    source_name: str
    identity: PublicationIdentity
    media_policy: MediaPolicy


class ContentItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    id: str | None = Field(default=None, min_length=1, max_length=200)
    title: str = Field(min_length=1)
    subtitle: str | None = None
    text: str | None = None
    city: str | None = None
    location: str | None = None
    address: str | None = None
    date: str | None = None
    time: str | None = None
    end_date: str | None = None
    image_width: int | None = Field(default=None, ge=1)
    image_height: int | None = Field(default=None, ge=1)
    image_url: str | None = None
    image_alt: str | None = None
    image_name: str | None = None
    link: str | None = None
    tags: list[str] = Field(default_factory=list)
    organizer: str | None = None
    price: str | None = None
    ticket_link: str | None = None
    # Bookkeeping is not a mapped field and is never exposed to Jinja.
    _source_context: SourceContext | None = PrivateAttr(default=None)

    @property
    def media_policy(self) -> MediaPolicy:
        return (
            self._source_context.media_policy if self._source_context else MediaPolicy()
        )

    @field_validator("title", "id")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Nonempty string required")
        return value

    @field_validator("tags", mode="before")
    @classmethod
    def missing_tags(cls, value):
        return [] if value is None else value

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(tag.strip() for tag in value if tag.strip()))

    @field_validator("image_url", "link", "ticket_link")
    @classmethod
    def valid_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or any(c.isspace() or ord(c) < 32 for c in value)
            ):
                raise ValueError("HTTP(S) URL without credentials required")
            parsed.port
        return value

    @field_validator("date", "end_date")
    @classmethod
    def valid_date(cls, value: str | None) -> str | None:
        if value is not None and (
            len(value) != 10 or calendar_date.fromisoformat(value).isoformat() != value
        ):
            raise ValueError("ISO calendar date required")
        return value

    @field_validator("time")
    @classmethod
    def valid_time(cls, value: str | None) -> str | None:
        if value is not None and (
            len(value) not in (5, 8) or clock_time.fromisoformat(value).tzinfo
        ):
            raise ValueError("Local ISO time required")
        return value

    @field_validator("image_name")
    @classmethod
    def safe_filename(cls, value: str | None) -> str | None:
        if value is not None and (
            len(value) > 200 or any(c in value for c in "/\\\r\n\x00")
        ):
            raise ValueError("Invalid image name")
        return value


class RenderedPost(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    text: str
    image_url: str | None = None
    image_alt: str | None = None
    image_name: str | None = None
    _source_context: SourceContext | None = PrivateAttr(default=None)

    @property
    def media_policy(self) -> MediaPolicy:
        return (
            self._source_context.media_policy if self._source_context else MediaPolicy()
        )

    _url = field_validator("image_url")(ContentItem.valid_url.__func__)
    _name = field_validator("image_name")(ContentItem.safe_filename.__func__)
