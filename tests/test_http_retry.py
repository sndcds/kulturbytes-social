from unittest.mock import patch

import click
import httpx
from dotenv_support import IsolatedEnvironmentTestCase

from kulturbytes_common.http import retry_delay, safe_get


class RetryTests(IsolatedEnvironmentTestCase):
    def test_transient_status_and_transport_retries(self):
        for initial in (503, 429, httpx.ReadTimeout("secret")):
            calls = []

            def respond(request):
                calls.append(request)
                if len(calls) == 1:
                    if isinstance(initial, Exception):
                        raise initial
                    return httpx.Response(initial, headers={"Retry-After": "999999"})
                return httpx.Response(200)

            with (
                httpx.Client(transport=httpx.MockTransport(respond)) as client,
                patch("kulturbytes_common.http.time.sleep") as sleep,
            ):
                self.assertEqual(
                    safe_get(client, "https://example.test").status_code, 200
                )
                self.assertEqual(len(calls), 2)
                self.assertLessEqual(sleep.call_args.args[0], 5)

    def test_exhaustion_permanent_errors_and_posts(self):
        for status, expected in [(503, 3), (400, 1), (401, 1)]:
            calls = []

            def respond(request):
                calls.append(request)
                return httpx.Response(status)

            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                safe_get(client, "https://example.test")
                self.assertEqual(len(calls), expected)
                calls.clear()
                client.post("https://example.test")
                self.assertEqual(len(calls), 1)
        with httpx.Client(
            transport=httpx.MockTransport(
                lambda r: (_ for _ in ()).throw(httpx.ConnectError("secret"))
            )
        ) as client:
            with self.assertRaises(click.ClickException) as error:
                safe_get(client, "https://example.test")
            self.assertNotIn("secret", str(error.exception))

    def test_retry_after_dates_are_clamped(self):
        for value in ("Wed, 21 Oct 2099 07:28:00 GMT", "-2", "invalid"):
            self.assertTrue(
                0
                <= retry_delay(httpx.Response(429, headers={"Retry-After": value}), 0)
                <= 5
            )

    def test_inherits_client_timeout_and_preserves_explicit_overrides(self):
        configured = httpx.Timeout(connect=10, read=61, write=62, pool=11)
        override = httpx.Timeout(connect=2, read=12, write=13, pool=3)
        for streaming in (False, True):
            for kwargs, expected in (
                ({}, configured.as_dict()),
                ({"timeout": override}, override.as_dict()),
                ({"timeout": None}, httpx.Timeout(None).as_dict()),
            ):
                seen = []

                def respond(request):
                    seen.append(request.extensions["timeout"])
                    return httpx.Response(503 if len(seen) == 1 else 200)

                with httpx.Client(
                    timeout=configured, transport=httpx.MockTransport(respond)
                ) as client:
                    response = safe_get(
                        client, "https://example.test", stream=streaming, **kwargs
                    )
                    response.close()
                self.assertEqual(seen, [expected, expected])
