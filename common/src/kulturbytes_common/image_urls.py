"""Validated, opt-in Pluto image URL settings; no downloads or local conversion."""

import re
from fractions import Fraction
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import click
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IMAGE_PLATFORMS = frozenset({"facebook", "instagram", "mastodon", "bluesky"})


class ImageSettings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    ratio: dict[str, str] = Field(default_factory=dict)
    type: dict[str, Literal["jpg", "png", "webp"]] = Field(default_factory=dict)
    max_width: int | None = Field(default=None, ge=1, le=65535)
    max_height: int | None = Field(default=None, ge=1, le=65535)

    @field_validator("ratio", "type")
    @classmethod
    def known_platforms(cls, values):
        unknown = set(values) - IMAGE_PLATFORMS
        if unknown:
            raise ValueError("Unknown image platform(s): " + ", ".join(sorted(unknown)))
        return values

    @field_validator("ratio")
    @classmethod
    def valid_ratios(cls, values):
        for value in values.values():
            if value != "free" and not re.fullmatch(
                r"[1-9][0-9]{0,4}[/:][1-9][0-9]{0,4}", value
            ):
                raise ValueError(
                    "Ratio must be free or positive integers separated by / or :"
                )
        return values

    @model_validator(mode="after")
    def nonzero_dimensions(self):
        for value in self.ratio.values():
            if value == "free":
                continue
            numerator, denominator = re.split(r"[/:]", value)
            aspect = Fraction(int(numerator), int(denominator))
            if aspect <= Fraction(1, 10000):
                raise ValueError("Ratio is below Pluto's supported minimum")
            if (self.max_width and self.max_width / aspect < 1) or (
                self.max_height and self.max_height * aspect < 1
            ):
                raise ValueError("Image limits would produce a zero-sized edge")
        return self


def image_url(
    url: str | None,
    settings: ImageSettings | None,
    platform: str,
    width: int | None = None,
    height: int | None = None,
) -> str | None:
    if (
        not url
        or settings is None
        or not (
            settings.ratio or settings.type or settings.max_width or settings.max_height
        )
    ):
        return url
    ratio = settings.ratio.get(platform, "free")
    params = {}
    if ratio != "free":
        numerator, denominator = re.split(r"[/:]", ratio)
        aspect = Fraction(int(numerator), int(denominator))
        params["ratio"] = f"{numerator}:{denominator}"
    elif settings.max_width or settings.max_height:
        if settings.max_width and settings.max_height and not (width and height):
            raise click.ClickException(
                "Freies Bildformat mit zwei Größenlimits benötigt image_width und image_height."
            )
        aspect = Fraction(width, height) if width and height else None
    else:
        aspect = None
    if aspect is not None and (settings.max_width or settings.max_height):
        # Send only the limiting edge: Pluto derives the other from the ratio.
        # Two independently supplied edges would override the requested crop ratio.
        if settings.max_width and (
            not settings.max_height
            or Fraction(settings.max_width, settings.max_height) <= aspect
        ):
            params["width"] = str(settings.max_width)
        else:
            params["height"] = str(settings.max_height)
    else:
        if settings.max_width:
            params["width"] = str(settings.max_width)
        if settings.max_height:
            params["height"] = str(settings.max_height)
    output_type = settings.type.get(platform)
    if output_type:
        params["type"] = output_type
    parts = urlsplit(url)
    managed = {"ratio", "width", "height", "fit"}
    if output_type:
        managed.add("type")
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in managed
    ]
    query.extend(params.items())
    return urlunsplit(parts._replace(query=urlencode(query)))
