from typing import Protocol

import httpx

from .models import RenderedPost as RenderedPost
from .models import SocialItem as SocialItem


class SourceAdapter(Protocol):
    name: str

    def list_items(
        self, client: httpx.Client, *, target: str | tuple[str, str] | None = None
    ) -> list[SocialItem]: ...
    def get_item(self, client: httpx.Client, item: SocialItem) -> SocialItem: ...
