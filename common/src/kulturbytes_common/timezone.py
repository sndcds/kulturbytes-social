"""Kulturbytes business dates always use Europe/Berlin."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Europe/Berlin")


def application_today(now: datetime | None = None) -> date:
    if now is not None and now.tzinfo is None:
        raise ValueError("An aware clock value is required.")
    return (now or datetime.now(TIMEZONE)).astimezone(TIMEZONE).date()
