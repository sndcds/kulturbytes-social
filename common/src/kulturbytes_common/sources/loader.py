"""Strict local source definitions; parsing never performs HTTP or credential lookup."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit

import jmespath
import yaml
from jmespath.exceptions import JMESPathError
from jmespath.parser import ParsedResult
from pydantic import BaseModel, ConfigDict, ValidationError

from ..network import MediaPolicy, MediaPolicyError, https_url
from .errors import SourceConfigurationError, SourceNotFound
from .models import ContentItem
from .paths import config_roots

if TYPE_CHECKING:
    from . import SourceAdapter

NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
SAFE_HEADERS = frozenset({"accept", "user-agent", "x-api-version"})


class SourceBehavior(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    skip_past: bool = False


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise ValueError("Invalid key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping
)


@dataclass(frozen=True)
class RequestDefinition:
    url: str
    root: ParsedResult
    mode: str = "collection"
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    fields: dict[str, ParsedResult] | None = None

    def item_url(self, item_id: str) -> str:
        # One opaque path segment; no format(), Jinja, query or origin substitution.
        if not item_id or item_id in (".", ".."):
            raise SourceConfigurationError("Ungültige ID für Detailabruf.")
        return self.url.replace("{id}", quote(item_id, safe=""))


@dataclass(frozen=True)
class SourceDefinition:
    name: str
    adapter: str
    listing: RequestDefinition | None
    detail: RequestDefinition | None
    fields: dict[str, ParsedResult]
    media: MediaPolicy
    behavior: SourceBehavior

    @property
    def root(self):
        return self.listing.root if self.listing else None


def mapping(name: str, fields: object) -> dict[str, ParsedResult]:
    if (
        not isinstance(fields, dict)
        or "title" not in fields
        or set(fields) - ContentItem.model_fields.keys()
    ):
        raise SourceConfigurationError(
            f"Quelle {name}: fields benötigt title und ausschließlich kanonische Felder."
        )
    return {key: expression(name, key, value) for key, value in fields.items()}


def expression(name: str, field: str, value: object) -> ParsedResult:
    try:
        if not isinstance(value, str) or not value.strip():
            raise ValueError
        return jmespath.compile(value)
    except (JMESPathError, ValueError):
        raise SourceConfigurationError(
            f"Quelle {name}: ungültiger JMESPath für {field}."
        ) from None


def static_strings(value: object, *, headers: bool = False) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError
    seen = set()
    for key, content in value.items():
        if not isinstance(key, str) or not key or not isinstance(content, str):
            raise ValueError
        if any(ord(char) < 32 or ord(char) == 127 for char in key + content):
            raise ValueError
        if headers:
            if key.lower() not in SAFE_HEADERS or key.lower() in seen:
                raise ValueError
            (key + content).encode("ascii")
            seen.add(key.lower())
    return value


def request_definition(
    name: str, raw: object, *, detail: bool = False
) -> RequestDefinition:
    try:
        if not isinstance(raw, dict) or set(raw) - {
            "url",
            "method",
            "headers",
            "query",
            "root",
            "mode",
            "fields",
        }:
            raise ValueError
        url = raw.get("url")
        if not isinstance(url, str):
            raise ValueError
        checked = url
        if detail:
            # Exactly one {id} in the path; braces anywhere else are rejected.
            if url.count("{id}") != 1 or "{id}" not in urlsplit(url).path:
                raise ValueError
            checked = url.replace("{id}", "placeholder")
        if "{" in checked or "}" in checked:
            raise ValueError
        https_url(checked)
        method = raw.get("method", "GET")
        mode = raw.get("mode", "object" if detail else "collection")
        if method != "GET" or mode not in ("collection", "object"):
            raise ValueError
        headers = static_strings(raw.get("headers", {}), headers=True)
        query = static_strings(raw.get("query", {}))
    except (ValueError, TypeError, UnicodeError, MediaPolicyError):
        raise SourceConfigurationError(
            f"Quelle {name}: ungültiger Request (HTTPS, GET, statische Header/Query, Modus oder Platzhalter)."
        ) from None
    return RequestDefinition(
        url,
        expression(name, "root", raw.get("root")),
        mode,
        method,
        headers,
        query,
        mapping(name, raw["fields"]) if "fields" in raw else None,
    )


def load_definition(path: Path) -> SourceDefinition:
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError, RecursionError):
        raise SourceConfigurationError("Ungültige YAML-Quellendefinition.") from None
    if not isinstance(raw, dict) or set(raw) - {
        "name",
        "adapter",
        "endpoint",
        "method",
        "headers",
        "query",
        "request",
        "list",
        "detail",
        "root",
        "mode",
        "fields",
        "media",
        "behavior",
    }:
        raise SourceConfigurationError("Unbekannte oder fehlende Quelleneinstellungen.")
    name = raw.get("name")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise SourceConfigurationError("Ungültiger Quellenname.")
    from .registry import ADAPTERS

    adapter = raw.get("adapter")
    if not isinstance(adapter, str) or adapter not in ADAPTERS:
        raise SourceConfigurationError(f"Quelle {name}: unbekannter Adapter.")
    try:
        media = MediaPolicy.model_validate(raw.get("media", {}))
        behavior = SourceBehavior.model_validate(raw.get("behavior", {}))
    except (ValidationError, ValueError):
        raise SourceConfigurationError(
            f"Quelle {name}: ungültige media- oder behavior-Konfiguration."
        ) from None
    if adapter != "json":
        if set(raw) - {"name", "adapter", "media", "behavior"}:
            raise SourceConfigurationError(
                f"Quelle {name}: der Adapter besitzt eigene Abrufregeln."
            )
        return SourceDefinition(name, adapter, None, None, {}, media, behavior)
    forms = [key for key in ("endpoint", "request", "list") if key in raw]
    if len(forms) != 1:
        raise SourceConfigurationError(
            f"Quelle {name}: genau eine von endpoint, request oder list angeben."
        )
    if forms[0] == "endpoint":
        listing = {
            key: raw[key]
            for key in ("method", "headers", "query", "root", "mode")
            if key in raw
        }
        listing["url"] = raw["endpoint"]
    else:
        if set(raw) & {"method", "headers", "query"}:
            raise SourceConfigurationError(
                f"Quelle {name}: Request-Einstellungen gehören in request/list."
            )
        listing = raw[forms[0]]
        if not isinstance(listing, dict):
            raise SourceConfigurationError(
                f"Quelle {name}: request/list muss ein Objekt sein."
            )
        if any(key in raw and key in listing for key in ("root", "mode")):
            raise SourceConfigurationError(
                f"Quelle {name}: root/mode nur einmal angeben."
            )
        listing = {
            **{key: raw[key] for key in ("root", "mode") if key in raw},
            **listing,
        }
    return SourceDefinition(
        name,
        adapter,
        request_definition(name, listing),
        request_definition(name, raw["detail"], detail=True)
        if "detail" in raw
        else None,
        mapping(name, raw.get("fields")),
        media,
        behavior,
    )


def definitions(roots: list[Path] | None = None) -> dict[str, SourceDefinition]:
    result = {}
    for root in config_roots("sources") if roots is None else roots:
        for path in sorted(root.glob("*.yaml")):
            if not path.resolve().is_relative_to(root.resolve()):
                raise SourceConfigurationError(
                    "Quellendatei außerhalb des Konfigurationsverzeichnisses."
                )
            definition = load_definition(path)
            if definition.name in result:
                raise SourceConfigurationError(
                    f"Doppelter Quellenname: {definition.name}."
                )
            result[definition.name] = definition
    return result


def load_source(name: str) -> "SourceAdapter":
    from .registry import ADAPTERS

    if not NAME.fullmatch(name):
        raise SourceNotFound("Unbekannte Quelle.")
    definition = definitions().get(name)
    if definition is None:
        raise SourceNotFound(f"Quelle {name} nicht gefunden.")
    return ADAPTERS[definition.adapter](definition)
