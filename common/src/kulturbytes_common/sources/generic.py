"""Configured JSON collections, optionally enriched using private list/detail context."""

from dataclasses import dataclass

import click
import httpx

from .errors import SourceNotFound, SourceValidationError
from .fetching import fetch
from .loader import RequestDefinition, SourceDefinition
from .mapping import evaluate, map_item
from .models import ContentItem, PublicationIdentity, SourceContext
from .rules import finite_number, safe_identity


@dataclass(frozen=True)
class SourceRecord:
    raw_list: dict
    preview: ContentItem


def safe_scalar(value: object) -> bool:
    if isinstance(value, str):
        return (
            bool(value.strip())
            and len(value) <= 200
            and all(ord(c) >= 32 and ord(c) != 127 for c in value)
        )
    return type(value) is bool or finite_number(value)


class JsonSourceAdapter:
    def __init__(self, definition: SourceDefinition) -> None:
        self.definition = definition
        self.name = definition.name
        self.behavior = definition.behavior
        self._resolved: set[int] = set()
        self._records: dict[int, SourceRecord] = {}

    @property
    def combined(self) -> bool:
        return bool(self.definition.detail and self.definition.detail.placeholders)

    def resolve_legacy_selector(self, selector: tuple[str | None, str | None]):
        if not any(value is not None for value in selector):
            return None
        if not self.definition.selectors:
            raise click.UsageError(
                "Diese Quelle unterstützt keine Legacy-Selektoren; bitte --item-id verwenden."
            )
        if any(value is None for value in selector):
            raise click.UsageError(
                "--event-uuid und --date-identifier müssen gemeinsam angegeben werden."
            )
        return selector

    def matches(self, raw: dict, target: str | tuple[str, str]) -> bool:
        if isinstance(target, tuple):
            return all(
                any(
                    evaluate(self.name, key, expr, raw) == value
                    for expr in self.definition.selectors[key]
                )
                for key, value in zip(("event_uuid", "date_identifier"), target)
            )
        expressions = self.definition.listing.fields or self.definition.fields
        expr = expressions.get("id")
        return expr is not None and evaluate(self.name, "id", expr, raw) == target

    def validate(self, request: RequestDefinition, raw: object) -> None:
        if not isinstance(raw, dict):
            raise SourceValidationError(
                f"Quelle {self.name}: Eintrag muss ein Objekt sein."
            )
        for assertion in request.assertions:
            assertion.validate(self.name, raw)

    def context(self, item: ContentItem, raw: dict) -> ContentItem:
        if self.definition.identity:
            values = {
                key: evaluate(self.name, key, expr, raw)
                for key, expr in self.definition.identity.items()
            }
            if not all(safe_identity(value) for value in values.values()):
                raise SourceValidationError(
                    f"Quelle {self.name}: ungültige Publikationsidentität."
                )
            identity = PublicationIdentity(**values)
        else:
            key = f"{self.name}:{item.id}" if item.id is not None else ""
            identity = PublicationIdentity(key, key, item.id or "")
        item._source_context = SourceContext(self.name, identity, self.definition.media)
        return item

    def allowed(self, raw: dict) -> bool:
        for expr, op, expected in self.definition.filters:
            value = evaluate(self.name, "filter", expr, raw)
            equal = type(value) is type(expected) and value == expected
            truthy = value not in (None, False, "", [], {}) or type(value) in (
                int,
                float,
            )
            if not {
                "equals": equal,
                "not_equals": not equal,
                "truthy": truthy,
                "falsy": not truthy,
            }[op]:
                return False
        return True

    def map_detail(self, raw: dict, *, listed: dict | None = None) -> ContentItem:
        request = self.definition.detail
        context = {"list": listed, "detail": raw} if self.combined else raw
        # Check relationships before field validation; never substitute a missing detail identity.
        for index, (left, right) in enumerate(request.identity_checks, 1):
            a = evaluate(self.name, "identity left", left, context)
            b = evaluate(self.name, "identity right", right, context)
            if (
                not safe_scalar(a)
                or not safe_scalar(b)
                or type(a) is not type(b)
                or a != b
            ):
                raise SourceValidationError(
                    f"Quelle {self.name}: Identitätsprüfung {index} fehlgeschlagen ({left.expression} / {right.expression}). Veröffentlichung abgebrochen."
                )
        self.validate(request, raw)
        item = map_item(
            self.name,
            request.fields or self.definition.fields,
            context,
            derived=self.definition.derived,
        )
        return self.context(item, context)

    def _detail(self, item_id: str, *, listed: dict | None = None) -> ContentItem:
        context = {"list": listed} if self.combined else None
        rows = fetch(
            self.name, self.definition.detail, item_id=item_id, context=context
        )
        if len(rows) != 1:
            raise SourceValidationError(f"Quelle {self.name}: Detail nicht eindeutig.")
        item = self.map_detail(rows[0], listed=listed)
        if item.id != item_id:
            raise SourceValidationError(
                f"Quelle {self.name}: Detail-ID stimmt nicht eindeutig mit der Auswahl überein."
            )
        self._resolved.add(id(item))
        # Retain the object so a reused Python id cannot mark another item resolved.
        self._records[id(item)] = SourceRecord(listed or {}, item)
        return item

    def list_items(
        self, client: httpx.Client, *, target: str | tuple | None = None
    ) -> list[ContentItem]:
        self._records.clear()
        self._resolved.clear()
        if isinstance(target, str) and self.definition.detail and not self.combined:
            return [self._detail(target)]
        request = self.definition.listing
        rows = fetch(self.name, request, skip_invalid=self.definition.skip_invalid)
        items = []
        matches = 0
        for index, raw in enumerate(rows, 1):
            matched = (
                target is not None
                and isinstance(raw, dict)
                and self.matches(raw, target)
            )
            try:
                self.validate(request, raw)
                item = map_item(
                    self.name,
                    request.fields or self.definition.fields,
                    raw,
                    derived=None if self.definition.detail else self.definition.derived,
                )
                self.context(item, {"list": raw} if self.combined else raw)
            except SourceValidationError:
                if matched or not self.definition.skip_invalid:
                    raise
                click.echo(
                    f"Quelle {self.name}: ungültiger Listeneintrag {index} übersprungen.",
                    err=True,
                )
                continue
            if matched:
                matches += 1
            if target is not None and not matched:
                continue
            if not self.allowed(raw):
                continue
            self._records[id(item)] = SourceRecord(raw, item)
            items.append(item)
        if target is not None and matches != 1:
            raise SourceNotFound(
                f"Quelle {self.name}: Auswahl nicht eindeutig gefunden."
            )
        ids = [item.id for item in items if item.id is not None]
        if not request.allow_duplicate_ids and len(ids) != len(set(ids)):
            raise SourceValidationError(f"Quelle {self.name}: doppelte id.")
        if self.definition.detail and any(item.id is None for item in items):
            raise SourceValidationError(
                f"Quelle {self.name}: Detailabruf benötigt id im Listen-Mapping."
            )
        return items

    def get_item(self, client: httpx.Client, item: ContentItem) -> ContentItem:
        if self.definition.detail and id(item) not in self._resolved:
            record = self._records.get(id(item))
            if self.combined and record is None:
                raise SourceValidationError(
                    f"Quelle {self.name}: privater Listenkontext fehlt."
                )
            detail = self._detail(item.id, listed=record.raw_list if record else None)
            if detail._source_context.identity != item._source_context.identity:
                raise SourceValidationError(
                    f"Quelle {self.name}: Publikationsidentität wurde im Detail verändert."
                )
            return detail
        return item
