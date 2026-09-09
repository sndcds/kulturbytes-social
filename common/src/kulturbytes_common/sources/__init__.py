"""The workflow depends on adapter capabilities, never configured source names."""

from typing import Any, Protocol

import httpx

from .loader import SourceBehavior, SourceDefinition
from .models import ContentItem as ContentItem
from .models import RenderedPost as RenderedPost


class SourceAdapter(Protocol):
    name: str
    definition: SourceDefinition
    behavior: SourceBehavior

    def resolve_legacy_selector(
        self, selector: tuple[str | None, str | None]
    ) -> Any: ...
    def list_items(
        self, client: httpx.Client, *, target: Any = None
    ) -> list[ContentItem]: ...
    def get_item(self, client: httpx.Client, item: ContentItem) -> ContentItem: ...
