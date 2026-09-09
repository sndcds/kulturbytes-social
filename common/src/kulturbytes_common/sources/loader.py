"""Trusted YAML definitions, strictly checked before any source HTTP request."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import jmespath
import yaml
from jmespath.exceptions import JMESPathError
from jmespath.parser import ParsedResult
from pydantic import ValidationError

from .errors import SourceConfigurationError, SourceNotFound
from .models import SocialItem
from .paths import config_roots

if TYPE_CHECKING:
    from . import SourceAdapter

NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    values = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in values:
            raise ValueError("Duplicate or non-string mapping key")
        values[key] = loader.construct_object(value_node, deep=deep)
    return values


UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping
)


@dataclass(frozen=True)
class SourceDefinition:
    name: str
    adapter: str
    endpoint: str | None
    root: ParsedResult | None
    fields: dict[str, ParsedResult]


def load_definition(path: Path) -> SourceDefinition:
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError, RecursionError):
        raise SourceConfigurationError("Ungültige YAML-Quellendefinition.") from None
    if not isinstance(raw, dict) or set(raw) - {
        "name",
        "adapter",
        "endpoint",
        "root",
        "fields",
    }:
        raise SourceConfigurationError("Unbekannte oder fehlende Quelleneinstellungen.")
    name = raw.get("name")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise SourceConfigurationError("Ungültiger Quellenname.")
    adapter = raw.get("adapter")
    if adapter == "kulturbytes":
        if set(raw) != {"name", "adapter"} or name != "kulturbytes":
            raise SourceConfigurationError(
                "Kulturbytes benötigt ausschließlich name: kulturbytes und adapter: kulturbytes."
            )
        return SourceDefinition(name, adapter, None, None, {})
    if adapter != "json":
        raise SourceConfigurationError(f"Quelle {name}: unbekannter Adapter.")
    try:
        SocialItem(title="endpoint", link=raw.get("endpoint"))
        if not raw.get("endpoint"):
            raise ValueError()
    except (ValidationError, ValueError):
        raise SourceConfigurationError(f"Quelle {name}: ungültiger endpoint.") from None
    fields = raw.get("fields")
    if (
        not isinstance(fields, dict)
        or "title" not in fields
        or set(fields) - SocialItem.model_fields.keys()
    ):
        raise SourceConfigurationError(
            f"Quelle {name}: fields benötigt title und ausschließlich kanonische Felder."
        )
    compiled = {}
    for field, expression in {"root": raw.get("root"), **fields}.items():
        if not isinstance(expression, str) or not expression.strip():
            raise SourceConfigurationError(
                f"Quelle {name}: {field} benötigt einen JMESPath-Ausdruck."
            )
        try:
            compiled[field] = jmespath.compile(expression)
        except JMESPathError:
            raise SourceConfigurationError(
                f"Quelle {name}: ungültiger JMESPath für {field}."
            ) from None
    return SourceDefinition(
        name, adapter, raw["endpoint"], compiled.pop("root"), compiled
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
    from .generic import JsonSourceAdapter
    from .kulturbytes import KulturbytesSourceAdapter

    if not NAME.fullmatch(name):
        raise SourceNotFound("Unbekannte Quelle.")
    definition = definitions().get(name)
    if definition is None:
        raise SourceNotFound(f"Quelle {name} nicht gefunden.")
    return (
        KulturbytesSourceAdapter()
        if definition.adapter == "kulturbytes"
        else JsonSourceAdapter(definition)
    )
