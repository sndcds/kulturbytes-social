"""Source-scoped HTTPS media with pinned DNS and per-origin TLS pools."""

from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import SplitResult, urljoin

import click
import httpx

from .http import safe_get
from .network import (
    MediaPolicy,
    MediaPolicyError,
    PinnedTransport,
    https_url,
    public_address,
)

MAX_REDIRECTS = 5


def _media_url(url: str, policy: MediaPolicy) -> SplitResult:
    parsed = https_url(url)
    host = httpx.URL(url).host.encode("idna").decode("ascii")
    if host not in policy.allowed_hosts:
        raise MediaPolicyError("Medien-Host ist für diese Quelle nicht freigegeben.")
    return parsed


def resolve_media_target(url: str, policy: MediaPolicy) -> str:
    _media_url(url, policy)
    return public_address(url)


def validate_media_url(url: str, policy: MediaPolicy) -> None:
    resolve_media_target(url, policy)


class PublicMediaTransport(PinnedTransport):
    def __init__(
        self,
        policy: MediaPolicy,
        transport: httpx.BaseTransport | None = None,
        *,
        factory=None,
    ):
        super().__init__(
            lambda url: resolve_media_target(url, policy),
            factory=(lambda: transport) if transport is not None else factory,
        )


def create_media_client(parent: httpx.Client, policy: MediaPolicy) -> httpx.Client:
    """Separate media transport: no proxies, API auth, cookies or custom upstream transport."""
    return httpx.Client(
        transport=PublicMediaTransport(policy),
        trust_env=False,
        follow_redirects=False,
        timeout=parent.timeout,
        headers={"User-Agent": "Content-Media-Publisher/1.0"},
    )


@contextmanager
def media_response(
    client: httpx.Client, url: str, policy: MediaPolicy
) -> Iterator[httpx.Response]:
    seen: set[str] = set()
    response = None
    try:
        # Reuse one dedicated connection pool for this redirect/retry chain.
        with create_media_client(client, policy) as media_client:
            for redirect in range(MAX_REDIRECTS + 1):
                _media_url(url, policy)
                canonical = str(httpx.URL(url))
                if canonical in seen:
                    raise click.ClickException("Medienabruf: Redirect-Schleife.")
                seen.add(canonical)
                response = safe_get(
                    media_client, canonical, stream=True, headers={"Accept": "*/*"}
                )
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    response.close()
                    if (
                        not location
                        or not location.strip()
                        or redirect == MAX_REDIRECTS
                    ):
                        raise click.ClickException(
                            "Medienabruf: ungültiger Redirect oder Redirect-Limit erreicht."
                        )
                    try:
                        _media_url(urljoin(canonical, location), policy)
                        url = urljoin(canonical, location)
                    except ValueError:
                        raise click.ClickException(
                            "Medienabruf: ungültiger Redirect."
                        ) from None
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError:
                    raise click.ClickException(
                        f"Medienabruf fehlgeschlagen (HTTP {response.status_code})."
                    ) from None
                yield response
                return
    except (httpx.RequestError, httpx.InvalidURL):
        raise click.ClickException(
            "Medienabruf fehlgeschlagen; ungültige Adresse oder Netzwerkfehler."
        ) from None
    finally:
        if response is not None:
            response.close()
