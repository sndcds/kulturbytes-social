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
from .rules import Assertion, compile_assertions

if TYPE_CHECKING:
    from . import SourceAdapter

NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
SAFE_HEADERS = frozenset({"accept", "user-agent", "x-api-version"})
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


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
        from .mapping import evaluate

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
            "placeholders",
            "assertions",
            "identity_checks",
            "allow_duplicate_ids",
        }:
            raise ValueError
        if not detail and raw.get("identity_checks"):
            raise ValueError
        if detail and raw.get("allow_duplicate_ids"):
            raise ValueError
        url = raw.get("url")
        if not isinstance(url, str):
            raise ValueError
        checked = url
        placeholders = raw.get("placeholders", {})
        if not isinstance(placeholders, dict) or (placeholders and not detail):
            raise ValueError
        if detail:
            names = PLACEHOLDER.findall(url)
            declared = set(placeholders) if placeholders else {"id"}
            if set(names) != declared or len(names) != len(declared):
                raise ValueError
            if names != PLACEHOLDER.findall(urlsplit(url).path):
                raise ValueError
            checked = PLACEHOLDER.sub("placeholder", url)
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
        {key: expression(name, key, value) for key, value in placeholders.items()},
        compile_assertions(name, raw.get("assertions", {}), expression),
        compile_checks(name, raw.get("identity_checks", [])),
        checked_bool(name, raw.get("allow_duplicate_ids", False)),
    )


def checked_bool(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise SourceConfigurationError(
            f"Quelle {name}: Boolesche Einstellung erwartet."
        )
    return value


def compile_checks(
    name: str, raw: object
) -> tuple[tuple[ParsedResult, ParsedResult], ...]:
    if not isinstance(raw, list):
        raise SourceConfigurationError(
            f"Quelle {name}: identity_checks muss eine Liste sein."
        )
    result = []
    for check in raw:
        if not isinstance(check, dict) or set(check) != {"left", "right"}:
            raise SourceConfigurationError(
                f"Quelle {name}: ungültige Identitätsprüfung."
            )
        result.append(
            tuple(expression(name, side, check[side]) for side in ("left", "right"))
        )
    return tuple(result)


def compile_identity(name: str, raw: object) -> dict[str, ParsedResult]:
    if not isinstance(raw, dict) or (
        raw and set(raw) != {"publication_key", "content_key", "revision"}
    ):
        raise SourceConfigurationError(
            f"Quelle {name}: ungültige publication identity."
        )
    return {key: expression(name, key, value) for key, value in raw.items()}


def compile_selectors(name: str, raw: object) -> dict[str, tuple[ParsedResult, ...]]:
    # The two existing CLI arguments are the only compatibility surface.
    if not isinstance(raw, dict) or (
        raw and set(raw) != {"event_uuid", "date_identifier"}
    ):
        raise SourceConfigurationError(f"Quelle {name}: ungültige Legacy-Selektoren.")
    result = {}
    for key, values in raw.items():
        if not isinstance(values, list) or not values:
            raise SourceConfigurationError(
                f"Quelle {name}: Selektor benötigt eine Ausdrucksliste."
            )
        result[key] = tuple(expression(name, key, value) for value in values)
    return result


def compile_filters(
    name: str, raw: object
) -> tuple[tuple[ParsedResult, str, object], ...]:
    if not isinstance(raw, list):
        raise SourceConfigurationError(f"Quelle {name}: filters muss eine Liste sein.")
    result = []
    for rule in raw:
        if not isinstance(rule, dict) or "expression" not in rule or len(rule) != 2:
            raise SourceConfigurationError(f"Quelle {name}: ungültiger Filter.")
        op = next(key for key in rule if key != "expression")
        value = rule[op]
        if op not in {"equals", "not_equals", "truthy", "falsy"} or type(value) not in (
            str,
            int,
            float,
            bool,
            type(None),
        ):
            raise SourceConfigurationError(f"Quelle {name}: ungültiger Filteroperator.")
        if op in {"truthy", "falsy"} and value is not True:
            raise SourceConfigurationError(
                f"Quelle {name}: truthy/falsy benötigt true."
            )
        result.append((expression(name, "filter", rule["expression"]), op, value))
    return tuple(result)


def compile_derived(
    name: str, raw: object
) -> dict[str, tuple[str | ParsedResult, ...]]:
    if not isinstance(raw, dict) or set(raw) - ContentItem.model_fields.keys():
        raise SourceConfigurationError(f"Quelle {name}: ungültige abgeleitete Felder.")
    result = {}
    for key, rule in raw.items():
        if (
            not isinstance(rule, dict)
            or set(rule) != {"concat"}
            or not isinstance(rule["concat"], list)
        ):
            raise SourceConfigurationError(f"Quelle {name}: derived benötigt concat.")
        parts = []
        for part in rule["concat"]:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and set(part) == {"expr"}:
                parts.append(expression(name, key, part["expr"]))
            else:
                raise SourceConfigurationError(
                    f"Quelle {name}: ungültiger concat-Teil."
                )
        result[key] = tuple(parts)
    return result


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
        "identity",
        "legacy_selectors",
        "filters",
        "derived",
        "skip_invalid",
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
    parsed_list = request_definition(name, listing)
    parsed_detail = (
        request_definition(name, raw["detail"], detail=True)
        if "detail" in raw
        else None
    )
    if parsed_detail and parsed_detail.placeholders and not parsed_list.fields:
        raise SourceConfigurationError(
            f"Quelle {name}: deklarierte Detail-Platzhalter benötigen list.fields für die Vorschau."
        )
    return SourceDefinition(
        name,
        adapter,
        parsed_list,
        parsed_detail,
        mapping(name, raw.get("fields")),
        media,
        behavior,
        compile_identity(name, raw.get("identity", {})),
        compile_selectors(name, raw.get("legacy_selectors", {})),
        compile_filters(name, raw.get("filters", [])),
        compile_derived(name, raw.get("derived", {})),
        checked_bool(name, raw.get("skip_invalid", False)),
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
