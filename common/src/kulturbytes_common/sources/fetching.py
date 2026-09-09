"""Unauthenticated, pinned public HTTPS retrieval of configured response shapes."""

import click
import httpx
from jmespath.exceptions import JMESPathError

from ..http import safe_get
from ..network import PinnedTransport
from .definitions import RequestDefinition
from .errors import SourceFetchError, SourceMappingError


def source_client() -> httpx.Client:
    return httpx.Client(
        transport=PinnedTransport(),
        timeout=httpx.Timeout(connect=10, read=60, write=60, pool=10),
        headers={"User-Agent": "Content-Source/1.0", "Accept": "application/json"},
        follow_redirects=False,
        trust_env=False,
    )


def fetch(
    name: str,
    request: RequestDefinition,
    *,
    item_id: str | None = None,
    context: dict | None = None,
    skip_invalid: bool = False,
) -> list[dict]:
    url = (
        request.item_url(item_id, context=context, source_name=name)
        if item_id is not None or context is not None
        else request.url
    )
    try:
        # A new client per fetch prevents even source cookies from crossing requests.
        with source_client() as client:
            response = safe_get(
                client,
                str(httpx.URL(url).copy_merge_params(request.query)),
                headers=request.headers,
            )
            response.raise_for_status()
            raw = response.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, click.ClickException):
        raise SourceFetchError(f"Quelle {name}: JSON-Abruf fehlgeschlagen.") from None
    try:
        value = request.root.search(raw)
    except JMESPathError:
        raise SourceMappingError(
            f"Quelle {name}: root-Auswertung fehlgeschlagen."
        ) from None
    if request.mode == "collection":
        if not isinstance(value, list) or (
            not skip_invalid and any(not isinstance(item, dict) for item in value)
        ):
            raise SourceMappingError(
                f"Quelle {name}: root muss eine Liste von Objekten ergeben."
            )
        return value
    if not isinstance(value, dict):
        raise SourceMappingError(f"Quelle {name}: root muss ein Objekt ergeben.")
    return [value]
