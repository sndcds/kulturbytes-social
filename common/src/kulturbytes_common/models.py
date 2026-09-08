"""Strict boundary models; publisher dictionaries remain a compatibility interface."""
from datetime import date, time
from typing import Annotated
from urllib.parse import urlsplit

import click
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator

Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=200, pattern=r'^[A-Za-z0-9_][A-Za-z0-9_.:-]*$')]


class APIModel(BaseModel):
    model_config = ConfigDict(strict=True, extra='ignore')

    @field_validator('start_date', 'end_date', check_fields=False)
    @classmethod
    def calendar_date(cls, value: str | None) -> str | None:
        if value is not None:
            if len(value) != 10 or date.fromisoformat(value).isoformat() != value:
                raise ValueError('Invalid calendar date')
        return value

    @field_validator('start_time', check_fields=False)
    @classmethod
    def local_time(cls, value: str | None) -> str | None:
        if value:
            parsed = time.fromisoformat(value)
            if parsed.tzinfo or len(value) not in (5, 8):
                raise ValueError('Invalid local event time')
        return value

    @field_validator('url', 'ticket_link', check_fields=False)
    @classmethod
    def public_link(cls, value: str | None) -> str | None:
        if value:
            parsed = urlsplit(value)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or parsed.password is not None or any(c.isspace() for c in value):
                raise ValueError('Invalid link')
            parsed.port
        return value


class EventSummary(APIModel):
    uuid: Identifier
    date_uuid: Identifier
    date_slug: Identifier
    release_status: StrictStr
    start_date: StrictStr
    start_time: StrictStr | None = None
    title: Annotated[str, Field(strict=True, min_length=1)]
    venue_name: StrictStr | None = None
    venue_city: StrictStr | None = None
    summary: StrictStr | None = None


class EventDate(APIModel):
    uuid: Identifier
    slug: Identifier
    start_date: StrictStr
    start_time: StrictStr | None = None
    end_date: StrictStr | None = None
    venue_name: StrictStr | None = None
    venue_street: StrictStr | None = None
    venue_house_number: StrictStr | None = None
    venue_postal_code: StrictStr | None = None
    venue_city: StrictStr | None = None
    ticket_link: StrictStr | None = None
    price_type: StrictStr | None = None
    min_price: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    max_price: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    currency: StrictStr | None = 'EUR'


class EventImage(APIModel):
    uuid: Identifier | None = None
    url: StrictStr | None = None
    alt: StrictStr | None = None


class EventImages(APIModel):
    main: EventImage | None = None


class EventDetail(APIModel):
    uuid: Identifier
    title: Annotated[str, Field(strict=True, min_length=1)]
    subtitle: StrictStr | None = None
    description: StrictStr | None = None
    summary: StrictStr | None = None
    org_name: StrictStr | None = None
    tags: list[StrictStr] | None = None
    images: EventImages | None = None
    date: EventDate


def validate_detail(payload: object) -> dict:
    try:
        if not isinstance(payload, dict) or 'data' not in payload:
            raise ValueError('Missing data')
        return EventDetail.model_validate(payload['data']).model_dump(exclude_unset=True)
    except (ValidationError, ValueError):
        raise click.ClickException('Kulturbytes: ungültige Detaildaten oder date_uuid/date-Struktur; Veröffentlichung abgebrochen.') from None


def validate_list(payload: object, *, target: tuple[str, str] | None = None) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get('data'), dict) or not isinstance(payload['data'].get('events'), list):
        raise click.ClickException('Kulturbytes: ungültige Listenantwort; data.events muss eine Liste sein.')
    valid = []
    for index, item in enumerate(payload['data']['events'], 1):
        try:
            valid.append(EventSummary.model_validate(item).model_dump(exclude_unset=True))
        except ValidationError:
            if target and isinstance(item, dict) and item.get('uuid') == target[0] and target[1] in (item.get('date_uuid'), item.get('date_slug')):
                raise click.ClickException('Kulturbytes: der direkt gewählte Termin enthält ungültige Listendaten.') from None
            click.echo(f'Kulturbytes: ungültiger Listeneintrag {index} übersprungen.', err=True)
    return valid
