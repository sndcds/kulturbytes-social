"""Source configuration values, independent of loading and adapter construction."""

import re
from dataclasses import dataclass, field
from urllib.parse import quote

from jmespath.parser import ParsedResult
from pydantic import BaseModel, ConfigDict

from ..network import MediaPolicy
from .errors import SourceConfigurationError
from .rules import Assertion, evaluate

PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class SourceBehavior(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    skip_past: bool = False


@dataclass(frozen=True)
class RequestDefinition:
    url: str
    root: ParsedResult
    mode: str = "collection"
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    fields: dict[str, ParsedResult] | None = None
    placeholders: dict[str, ParsedResult] = field(default_factory=dict)

    assertions: tuple[Assertion, ...] = ()
    identity_checks: tuple[tuple[ParsedResult, ParsedResult], ...] = ()
    allow_duplicate_ids: bool = False

    def item_url(
        self,
        item_id: str | None = None,
        *,
        context: dict | None = None,
        source_name: str = "JSON",
    ) -> str:
        # One opaque path segment; no format(), Jinja, query or origin substitution.
        values = (
            {
                key: evaluate(source_name, key, expr, context)
                for key, expr in self.placeholders.items()
            }
            if self.placeholders
            else {"id": item_id}
        )
        for key, value in values.items():
            if not isinstance(value, str) or not value.strip() or value in (".", ".."):
                raise SourceConfigurationError(
                    f"Quelle {source_name}: ungültiger Detail-Platzhalter {key}."
                )
        return PLACEHOLDER.sub(lambda match: quote(values[match[1]], safe=""), self.url)


@dataclass(frozen=True)
class SourceDefinition:
    name: str
    adapter: str
    listing: RequestDefinition
    detail: RequestDefinition | None
    fields: dict[str, ParsedResult]
    media: MediaPolicy
    behavior: SourceBehavior

    identity: dict[str, ParsedResult] = field(default_factory=dict)
    selectors: dict[str, tuple[ParsedResult, ...]] = field(default_factory=dict)
    filters: tuple[tuple[ParsedResult, str, object], ...] = ()
    derived: dict[str, tuple[str | ParsedResult, ...]] = field(default_factory=dict)
    skip_invalid: bool = False

    @property
    def root(self):
        return self.listing.root if self.listing else None
