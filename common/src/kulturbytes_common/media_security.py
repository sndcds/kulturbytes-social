"""Public HTTPS media only; DNS is rechecked before each request and redirect."""
import ipaddress
import socket
from contextlib import contextmanager
from urllib.parse import urljoin, urlsplit

import click
import httpx

from .http import safe_get

MAX_REDIRECTS = 5


def validate_media_url(url: str) -> None:
    try:
        if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url):
            raise ValueError
        parsed = urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme != 'https' or not host or parsed.username is not None or parsed.password is not None
                or parsed.fragment or '%' in host or host.rstrip('.').lower() == 'localhost'
                or host.rstrip('.').lower().endswith('.localhost')):
            raise ValueError
        port = parsed.port or 443
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            addresses = [ipaddress.ip_address(record[4][0]) for record in records]
        if not addresses:
            raise ValueError
        for address in addresses:
            address = getattr(address, 'ipv4_mapped', None) or address
            if (not address.is_global or address.is_multicast or address.is_reserved
                    or address.is_unspecified or address.is_loopback or address.is_link_local):
                raise ValueError
    except (ValueError, TypeError, OSError):
        raise click.ClickException('Medien-URL verweist auf ein nicht erlaubtes oder nicht auflösbares Netzwerkziel.') from None


@contextmanager
def media_response(client: httpx.Client, url: str):
    seen = set()
    response = None
    try:
        for redirect in range(MAX_REDIRECTS + 1):
            validate_media_url(url)
            canonical = str(httpx.URL(url))
            if canonical in seen:
                raise click.ClickException('Medienabruf: Redirect-Schleife.')
            seen.add(canonical)
            response = safe_get(client, canonical, stream=True, before_request=validate_media_url,
                                headers={'Accept': '*/*'})
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get('Location')
                response.close()
                if not location or not location.strip() or redirect == MAX_REDIRECTS:
                    raise click.ClickException('Medienabruf: ungültiger Redirect oder Redirect-Limit erreicht.')
                try:
                    url = urljoin(canonical, location)
                except ValueError:
                    raise click.ClickException("Medienabruf: ungültiger Redirect.") from None
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
