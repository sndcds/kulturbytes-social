from unittest.mock import patch
import click
import httpx
from dotenv_support import IsolatedEnvironmentTestCase
from kulturbytes_common.http import safe_get, retry_delay


class RetryTests(IsolatedEnvironmentTestCase):
    def test_transient_status_and_transport_retries(self):
        for initial in (503, 429, httpx.ReadTimeout('secret')):
            calls = []
            def respond(request):
                calls.append(request)
                if len(calls) == 1:
                    if isinstance(initial, Exception):
                        raise initial
                    return httpx.Response(initial, headers={'Retry-After': '999999'})
                return httpx.Response(200)
            with httpx.Client(transport=httpx.MockTransport(respond)) as client, patch('kulturbytes_common.http.time.sleep') as sleep:
                self.assertEqual(safe_get(client, 'https://example.test').status_code, 200)
                self.assertEqual(len(calls), 2)
                self.assertLessEqual(sleep.call_args.args[0], 5)

    def test_exhaustion_permanent_errors_and_posts(self):
        for status, expected in [(503, 3), (400, 1), (401, 1)]:
            calls = []
            def respond(request):
                calls.append(request)
                return httpx.Response(status)
            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                safe_get(client, 'https://example.test')
                self.assertEqual(len(calls), expected)
                calls.clear()
                client.post('https://example.test')
                self.assertEqual(len(calls), 1)
        with httpx.Client(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError('secret')))) as client:
            with self.assertRaises(click.ClickException) as error:
                safe_get(client, 'https://example.test')
            self.assertNotIn('secret', str(error.exception))

    def test_retry_after_dates_are_clamped(self):
        for value in ('Wed, 21 Oct 2099 07:28:00 GMT', '-2', 'invalid'):
            self.assertTrue(0 <= retry_delay(httpx.Response(429, headers={'Retry-After': value}), 0) <= 5)
