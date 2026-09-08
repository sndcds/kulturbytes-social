"""Opt-in bounded retries for GET only. No mutation API is exposed here."""
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from collections.abc import Callable

import click
import httpx

RETRY_STATUSES = {429, 502, 503, 504}
RETRY_ERRORS = (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError)
MAX_ATTEMPTS = 3
MAX_DELAY = 5.0


def retry_delay(response: httpx.Response | None, attempt: int) -> float:
    fallback = min(MAX_DELAY, 0.5 * 2 ** attempt)
    value = response.headers.get('Retry-After') if response is not None else None
    if value:
        try:
            seconds = float(int(value))
        except (ValueError, OverflowError):
            try:
                stamp = parsedate_to_datetime(value)
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                seconds = (stamp - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                return fallback
        return max(0.0, min(MAX_DELAY, seconds))
    return fallback


def safe_get(client: httpx.Client, url: str, *, stream: bool = False,
             before_request: Callable[[str], None] | None = None, **kwargs) -> httpx.Response:
    kwargs.pop('follow_redirects', None)
    # Bound retry count, delay and each network phase. Retries reuse the client.
    kwargs.setdefault('timeout', httpx.Timeout(5.0))
    for attempt in range(MAX_ATTEMPTS):
        if before_request:
            before_request(url)
        try:
            if stream:
                response = client.send(client.build_request('GET', url, **kwargs), stream=True, follow_redirects=False)
            else:
                response = client.get(url, follow_redirects=False, **kwargs)
        except RETRY_ERRORS:
            if attempt == MAX_ATTEMPTS - 1:
                raise click.ClickException('HTTP-Lesezugriff fehlgeschlagen: Netzwerkfehler nach begrenzten Versuchen.') from None
            time.sleep(retry_delay(None, attempt))
            continue
        except httpx.RequestError:
            raise click.ClickException('HTTP-Lesezugriff fehlgeschlagen: Netzwerkfehler.') from None
        if response.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS - 1:
            return response
        delay = retry_delay(response, attempt)
        response.close()
        time.sleep(delay)
    raise AssertionError('Unreachable')
