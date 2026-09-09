"""Configured JSON collections; sources never inherit a publisher's HTTP state."""

import click
import httpx
from jmespath.exceptions import JMESPathError

from kulturbytes_common.http import safe_get

from .errors import SourceMappingError, SourceNotFound, SourceValidationError
from .loader import SourceDefinition
from .mapping import map_item
from .models import PublicationIdentity, SocialItem


def source_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(connect=10, read=60, write=60, pool=10),
        headers={
            "User-Agent": "Kulturbytes-Social-Source/1.0",
            "Accept": "application/json",
        },
        follow_redirects=False,
        trust_env=False,
    )


class JsonSourceAdapter:
    def __init__(self, definition: SourceDefinition) -> None:
        self.definition = definition
        self.name = definition.name

    def list_items(
        self, client: httpx.Client, *, target: str | tuple[str, str] | None = None
    ) -> list[SocialItem]:
        # Deliberately ignore the caller's client: no social auth, cookies, proxies or netrc.
        try:
            with source_client() as source:
                response = safe_get(source, self.definition.endpoint)
                response.raise_for_status()
                raw = response.json()
            collection = self.definition.root.search(raw)
        except (httpx.HTTPError, ValueError, JMESPathError, click.ClickException):
            raise SourceMappingError(
                f"Quelle {self.name}: JSON-Abruf oder root-Auswertung fehlgeschlagen."
            ) from None
        if not isinstance(collection, list):
            raise SourceMappingError(
                f"Quelle {self.name}: root muss eine Liste ergeben."
            )
        items = [map_item(self.name, self.definition.fields, raw) for raw in collection]
        ids = [item.id for item in items if item.id is not None]
        if len(ids) != len(set(ids)):
            raise SourceValidationError(f"Quelle {self.name}: doppelte id.")
        for item in items:
            key = f"{self.name}:{item.id}" if item.id is not None else ""
            item._origin = PublicationIdentity(self.name, key, key, item.id or "")
        if target is not None:
            items = [item for item in items if item.id == target]
            if len(items) != 1:
                raise SourceNotFound(
                    f"Quelle {self.name}: item-id nicht eindeutig gefunden."
                )
        return items

    def get_item(self, client: httpx.Client, item: SocialItem) -> SocialItem:
        return item
