"""Configured content collections and objects, optionally enriched through detail GETs."""

import click
import httpx

from .errors import SourceNotFound, SourceValidationError
from .fetching import fetch
from .loader import RequestDefinition, SourceDefinition
from .mapping import map_item
from .models import ContentItem, PublicationIdentity, SourceContext


class JsonSourceAdapter:
    def __init__(self, definition: SourceDefinition) -> None:
        self.definition = definition
        self.name = definition.name
        self.behavior = definition.behavior
        self._resolved: set[int] = set()

    def resolve_legacy_selector(self, selector: tuple[str | None, str | None]):
        if any(value is not None for value in selector):
            raise click.UsageError(
                "Diese Quelle unterstützt keine Legacy-Selektoren; bitte --item-id verwenden."
            )
        return None

    def _items(
        self, request: RequestDefinition, *, item_id: str | None = None
    ) -> list[ContentItem]:
        items = [
            map_item(self.name, request.fields or self.definition.fields, raw)
            for raw in fetch(self.name, request, item_id=item_id)
        ]
        ids = [item.id for item in items if item.id is not None]
        if len(ids) != len(set(ids)):
            raise SourceValidationError(f"Quelle {self.name}: doppelte id.")
        for item in items:
            key = f"{self.name}:{item.id}" if item.id is not None else ""
            item._source_context = SourceContext(
                self.name,
                PublicationIdentity(key, key, item.id or ""),
                self.definition.media,
            )
        return items

    def _detail(self, item_id: str) -> ContentItem:
        items = self._items(self.definition.detail, item_id=item_id)
        # A detail response must identify exactly the requested item, not silently redirect identity.
        if len(items) != 1 or items[0].id != item_id:
            raise SourceValidationError(
                f"Quelle {self.name}: Detail-ID stimmt nicht eindeutig mit der Auswahl überein."
            )
        self._resolved.add(id(items[0]))
        return items[0]

    def list_items(
        self, client: httpx.Client, *, target: str | None = None
    ) -> list[ContentItem]:
        if target is not None and self.definition.detail:
            return [self._detail(target)]
        items = self._items(self.definition.listing)
        if self.definition.detail and any(item.id is None for item in items):
            raise SourceValidationError(
                f"Quelle {self.name}: Detailabruf benötigt id im Listen-Mapping."
            )
        if target is not None:
            items = [item for item in items if item.id == target]
            if len(items) != 1:
                raise SourceNotFound(
                    f"Quelle {self.name}: item-id nicht eindeutig gefunden."
                )
        return items

    def get_item(self, client: httpx.Client, item: ContentItem) -> ContentItem:
        if self.definition.detail and id(item) not in self._resolved:
            return self._detail(item.id)
        return item
