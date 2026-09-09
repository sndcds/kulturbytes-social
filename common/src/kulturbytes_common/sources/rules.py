"""Small compiled JSON assertions and deterministic mapping functions."""

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, time
from urllib.parse import quote

import jmespath
from jmespath import functions
from jmespath.exceptions import JMESPathError
from jmespath.parser import ParsedResult

from .errors import SourceConfigurationError, SourceMappingError, SourceValidationError
from .models import ContentItem


class MappingFunctions(functions.Functions):
    @functions.signature({"types": ["string", "null"]})
    def _func_trim(self, value):
        return (value or "").strip()

    @functions.signature({"types": ["string"]}, {"types": ["array"]})
    def _func_join_text(self, separator, values):
        if any(value is not None and not isinstance(value, str) for value in values):
            raise ValueError
        return separator.join(
            value.strip() for value in values if value and value.strip()
        )

    @functions.signature({"types": ["number", "null"]})
    def _func_number_text(self, value):
        return "" if value is None else f"{value:g}"

    @functions.signature({"types": ["string"]})
    def _func_time_hm(self, value):
        parsed = time.fromisoformat(value)
        if parsed.tzinfo or len(value) not in (5, 8):
            raise ValueError
        return value[:5]

    @functions.signature({"types": ["string"]})
    def _func_path_segment(self, value):
        if not value.strip() or value in (".", ".."):
            raise ValueError
        return quote(value, safe="")


OPTIONS = jmespath.Options(custom_functions=MappingFunctions())


def evaluate(name: str, field: str, expression: ParsedResult, raw: object):
    try:
        return expression.search(raw, options=OPTIONS)
    except (JMESPathError, ValueError, TypeError, OverflowError):
        raise SourceMappingError(
            f"Quelle {name}: Mapping für {field} fehlgeschlagen."
        ) from None


def finite_number(value: object) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def safe_identity(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 200
        and bool(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.:-]*", value))
    )


@dataclass(frozen=True)
class Assertion:
    expression: ParsedResult
    label: str
    kind: str
    required: bool = False

    def validate(self, name: str, raw: dict) -> None:
        value = evaluate(name, self.label, self.expression, raw)
        valid = True
        if value is None or (
            self.required and isinstance(value, str) and not value.strip()
        ):
            valid = not self.required
        elif self.kind == "identifier":
            valid = safe_identity(value)
        elif self.kind == "string":
            valid = isinstance(value, str) and (
                not self.required or bool(value.strip())
            )
        elif self.kind == "object":
            valid = isinstance(value, dict)
        elif self.kind == "strings":
            valid = isinstance(value, list) and all(isinstance(v, str) for v in value)
        elif self.kind == "number":
            valid = finite_number(value) and value >= 0
        elif self.kind in ("date", "time", "url"):
            try:
                if not isinstance(value, str):
                    raise ValueError
                if self.kind == "date":
                    valid = (
                        len(value) == 10
                        and date.fromisoformat(value).isoformat() == value
                    )
                elif self.kind == "time":
                    valid = not value or (
                        len(value) in (5, 8) and not time.fromisoformat(value).tzinfo
                    )
                elif value:
                    ContentItem.valid_url(value)
            except (ValueError, TypeError):
                valid = False
        if not valid:
            raise SourceValidationError(
                f"Quelle {name}: ungültiger erforderlicher/optionaler Wert {self.label}."
            )


def compile_assertions(
    name: str,
    raw: object,
    compile_expression: Callable[[str, str, object], ParsedResult],
) -> tuple[Assertion, ...]:
    if not isinstance(raw, dict):
        raise SourceConfigurationError(
            f"Quelle {name}: assertions muss ein Objekt sein."
        )
    result = []
    for label, rule in raw.items():
        if (
            not isinstance(rule, dict)
            or set(rule) - {"type", "required"}
            or not isinstance(rule.get("type"), str)
            or rule.get("type")
            not in {
                "identifier",
                "string",
                "object",
                "strings",
                "number",
                "date",
                "time",
                "url",
            }
            or type(rule.get("required", False)) is not bool
        ):
            raise SourceConfigurationError(f"Quelle {name}: ungültige assertion.")
        result.append(
            Assertion(
                compile_expression(name, label, label),
                label,
                rule["type"],
                rule.get("required", False),
            )
        )
    return tuple(result)
