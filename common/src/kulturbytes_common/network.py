"""Public HTTPS destinations, DNS pinning and pools isolated by logical origin."""

import ipaddress
import re
import socket
from collections.abc import Callable
from urllib.parse import SplitResult, urlsplit

import click
import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MediaPolicyError(click.ClickException):
    pass


class MediaPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    allowed_hosts: frozenset[str] = Field(default_factory=frozenset)

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def hosts(cls, values):
        if not isinstance(values, (list, tuple, set, frozenset)):
            raise ValueError("Host collection required")
        normalized = []
        for value in values:
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError("Invalid host")
            host = value.encode("idna").decode("ascii").lower()
            if len(host) > 253 or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
                for part in host.split(".")
            ):
                raise ValueError(
                    "DNS host without scheme, credentials, path or port required"
                )
            normalized.append(host)
        return frozenset(normalized)


def https_url(url: str) -> SplitResult:
    try:
        if (
            not isinstance(url, str)
            or any(c.isspace() or ord(c) < 32 for c in url)
            or "\\" in url
        ):
            raise ValueError
        httpx.URL(url)  # Validate HTTPX/IDNA parsing at the configuration boundary too.
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or parsed.port not in (None, 443)
        ):
            raise ValueError
        return parsed
    except (ValueError, TypeError, httpx.InvalidURL):
        raise MediaPolicyError(
            "URL benötigt HTTPS auf Port 443 ohne Zugangsdaten oder Fragment."
        ) from None


def public_address(url: str) -> str:
    parsed = https_url(url)
    try:
        addresses = [
            ipaddress.ip_address(record[4][0])
            for record in socket.getaddrinfo(
                parsed.hostname, 443, type=socket.SOCK_STREAM
            )
        ]
        if not addresses:
            raise ValueError
        for original in addresses:
            address = getattr(original, "ipv4_mapped", None) or original
            if (
                not address.is_global
                or address.is_multicast
                or address.is_reserved
                or address.is_unspecified
                or address.is_loopback
                or address.is_link_local
            ):
                raise ValueError
        return str(addresses[0])
    except (ValueError, TypeError, OSError):
        raise MediaPolicyError(
            "URL verweist auf ein nicht erlaubtes oder nicht auflösbares Netzwerkziel."
        ) from None


class PinnedTransport(httpx.BaseTransport):
    """No IP-keyed pool is shared across different TLS server names.

    Validate DNS on every retry/request, then pass the numeric TCP destination and
    original SNI to HTTPcore. The factory is only a test seam, never YAML configuration.
    """

    def __init__(
        self,
        validate: Callable[[str], str] = public_address,
        *,
        factory: Callable[[], httpx.BaseTransport] | None = None,
    ):
        self.validate = validate
        self.factory = factory or (
            lambda: httpx.HTTPTransport(verify=True, trust_env=False, retries=0)
        )
        self.pools: dict[tuple[str, str, int], httpx.BaseTransport] = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        address = self.validate(str(request.url))
        origin = (request.url.scheme, request.url.host, request.url.port or 443)
        if origin not in self.pools:
            self.pools[origin] = self.factory()
        headers = request.headers.copy()
        headers["Host"] = request.url.netloc.decode("ascii")
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=address),
            headers=headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": request.url.host},
        )
        return self.pools[origin].handle_request(pinned)

    def close(self) -> None:
        for pool in self.pools.values():
            pool.close()
        self.pools.clear()
