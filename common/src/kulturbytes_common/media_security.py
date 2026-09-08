"""Allowlisted HTTPS media, connected to validated IPs with original Host and TLS SNI."""
from collections.abc import Iterator
import ipaddress
import socket
from contextlib import contextmanager
from urllib.parse import urljoin, urlsplit, SplitResult

import click
import httpx

from .http import safe_get

MAX_REDIRECTS = 5
# The actual Kulturbytes media origin in repository examples; no speculative CDNs.
MEDIA_HOSTS = frozenset({'api.kulturbytes.de'})


def _media_url(url: str) -> SplitResult:
    try:
        if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url):
            raise ValueError
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname not in MEDIA_HOSTS
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment or parsed.port not in (None, 443)):
            raise ValueError
        return parsed
    except (ValueError, TypeError):
        raise click.ClickException('Medien-URL ist kein erlaubter Kulturbytes-HTTPS-Endpunkt.') from None


def resolve_media_target(url: str) -> str:
    """Resolve once, reject any unsafe answer, and return the exact connection IP."""
    parsed = _media_url(url)
    try:
        records = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        addresses = [ipaddress.ip_address(record[4][0]) for record in records]
        if not addresses:
            raise ValueError
        for address in addresses:
            address = getattr(address, 'ipv4_mapped', None) or address
            if (not address.is_global or address.is_multicast or address.is_reserved
                    or address.is_unspecified or address.is_loopback or address.is_link_local):
                raise ValueError
        return str(addresses[0])
    except (ValueError, TypeError, OSError):
        raise click.ClickException('Medien-URL verweist auf ein nicht erlaubtes oder nicht auflösbares Netzwerkziel.') from None


def validate_media_url(url: str) -> None:
    resolve_media_target(url)


class PublicMediaTransport(httpx.BaseTransport):
    """Use HTTPX's transport plus HTTPcore's SNI extension, without custom sockets.

    The single allowed origin avoids sharing an IP-keyed TLS connection between
    different server names. Do not add hosts without revisiting that pool boundary.
    The optional transport is a test seam, never supplied by runtime configuration.
    """
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport if transport is not None else httpx.HTTPTransport(
            verify=True, trust_env=False, retries=0,
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        address = resolve_media_target(str(request.url))
        headers = request.headers.copy()
        headers['Host'] = request.url.netloc.decode('ascii')
        # Numeric URL fixes the TCP destination; SNI also controls certificate hostname validation.
        pinned = httpx.Request(
            request.method, request.url.copy_with(host=address), headers=headers, stream=request.stream,
            extensions={**request.extensions, 'sni_hostname': request.url.host},
        )
        return self._transport.handle_request(pinned)

    def close(self) -> None:
        self._transport.close()


def create_media_client(parent: httpx.Client) -> httpx.Client:
    """Separate media transport: no proxies, API auth, cookies or custom upstream transport."""
    return httpx.Client(
        transport=PublicMediaTransport(), trust_env=False, follow_redirects=False,
        timeout=parent.timeout,
        headers={'User-Agent': parent.headers.get('User-Agent', 'Kulturbytes-Media-Publisher/1.0')},
    )


@contextmanager
def media_response(client: httpx.Client, url: str) -> Iterator[httpx.Response]:
    seen: set[str] = set()
    response = None
    try:
        # Reuse one dedicated connection pool for this redirect/retry chain.
        with create_media_client(client) as media_client:
            for redirect in range(MAX_REDIRECTS + 1):
                _media_url(url)
                canonical = str(httpx.URL(url))
                if canonical in seen:
                    raise click.ClickException('Medienabruf: Redirect-Schleife.')
                seen.add(canonical)
                response = safe_get(media_client, canonical, stream=True, headers={'Accept': '*/*'})
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get('Location')
                    response.close()
                    if not location or not location.strip() or redirect == MAX_REDIRECTS:
                        raise click.ClickException('Medienabruf: ungültiger Redirect oder Redirect-Limit erreicht.')
                    try:
                        _media_url(urljoin(canonical, location))
                        url = urljoin(canonical, location)
                    except ValueError:
                        raise click.ClickException('Medienabruf: ungültiger Redirect.') from None
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError:
                    raise click.ClickException(f'Medienabruf fehlgeschlagen (HTTP {response.status_code}).') from None
                yield response
                return
    except (httpx.RequestError, httpx.InvalidURL):
        raise click.ClickException('Medienabruf fehlgeschlagen; ungültige Adresse oder Netzwerkfehler.') from None
    finally:
        if response is not None:
            response.close()
