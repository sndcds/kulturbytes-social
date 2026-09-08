"""HTTP-only CLI transport. Mutating requests are never retried."""
from urllib.parse import urlsplit
from typing import Any
from kulturbytes_common.auth import redact
import click
import httpx
from kulturbytes_common.environment import get_config
from kulturbytes_common.http import safe_get


class APIClient:
    def __enter__(self) -> "APIClient":
        url = get_config('KULTURBYTES_SOCIAL_API_URL', 'http://127.0.0.1:8000')
        token = get_config('KULTURBYTES_SOCIAL_API_TOKEN')
        try:
            parsed = urlsplit(url)
            parsed.port
        except ValueError:
            raise click.ClickException('Ungültige KULTURBYTES_SOCIAL_API_URL.') from None
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise click.ClickException('Ungültige KULTURBYTES_SOCIAL_API_URL.')
        if not token:
            raise click.ClickException('KULTURBYTES_SOCIAL_API_TOKEN fehlt.')
        self.token = token
        self.client = httpx.Client(base_url=url.rstrip('/') + '/api/v1/',
            headers={'Authorization': 'Bearer ' + token, 'User-Agent': 'Kulturbytes-Social-CLI/1.0'},
            timeout=httpx.Timeout(connect=10, read=600, write=60, pool=10), follow_redirects=False)
        return self

    def __exit__(self, *args: Any) -> None:
        self.client.close()

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = safe_get(self.client, path, **kwargs) if method == 'GET' else self.client.post(path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json()['detail']
                code = detail.get('code', 'request_failed')
                message = detail.get('message', 'Backend-Anfrage fehlgeschlagen.')
                attempt = detail.get('attempt_id')
                text = f'{code}: {message}' + (f' (Versuch {attempt})' if attempt else '')
                text = redact(text, self.token)
            except (ValueError, KeyError, AttributeError, TypeError):
                text = 'Backend-Anfrage fehlgeschlagen.'
            raise click.ClickException(text) from None
        except httpx.HTTPError:
            raise click.ClickException('Backend nicht erreichbar oder Antwort ausgeblieben. Bei Veröffentlichung zuerst das Journal prüfen; nicht ungeprüft wiederholen.') from None
        try:
            return response.json()
        except ValueError:
            raise click.ClickException('Ungültige Backend-Antwort.') from None

    def get(self, path: str, **params: Any) -> Any:
        return self.request('GET', path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, body: dict | None = None) -> Any:
        return self.request('POST', path, json=body or {})
