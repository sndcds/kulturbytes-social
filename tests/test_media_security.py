import socket
from unittest.mock import patch
import click
import httpx
from dotenv_support import IsolatedEnvironmentTestCase
from kulturbytes_common.media_security import validate_media_url, media_response


class MediaSecurityTests(IsolatedEnvironmentTestCase):
    def test_nonpublic_literals_and_credentials_rejected(self):
        bad = ['localhost', '127.0.0.1', '10.0.0.1', '192.168.1.1', '172.16.0.1', '169.254.169.254',
               '0.0.0.0', '224.0.0.1', '192.0.2.1', '[::1]', '[::]', '[fc00::1]', '[fe80::1]',
               '[ff02::1]', '[::ffff:127.0.0.1]', 'user:password@example.test']
        for host in bad:
            with self.subTest(host=host), self.assertRaises(click.ClickException):
                validate_media_url('https://'+host+'/image.jpg')
        for url in ('http://example.test/image', 'file:///image', 'https://example.test:bad/image'):
            with self.assertRaises(click.ClickException):
                validate_media_url(url)
        validate_media_url('https://8.8.8.8/image')
        validate_media_url('https://public.example/image')

    def test_dns_mixed_private_and_recheck_each_retry(self):
        def records(*ips):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in ips]
        for ips in [('10.0.0.1',), ('8.8.8.8', '127.0.0.1')]:
            with patch('socket.getaddrinfo', return_value=records(*ips)), self.assertRaises(click.ClickException):
                validate_media_url('https://example.test/image')
        calls = []
        with patch('socket.getaddrinfo', side_effect=[records('8.8.8.8'), records('8.8.8.8'), records('127.0.0.1')]), \
             httpx.Client(transport=httpx.MockTransport(lambda r: (calls.append(r), httpx.Response(503))[1])) as client:
            with self.assertRaises(click.ClickException):
                with media_response(client, 'https://example.test/image'):
                    pass
        self.assertEqual(len(calls), 1)

    def test_redirect_validation_and_limits(self):
        for location in ('https://127.0.0.1/image', '/start', '', 'https://user:pass@example.test/x', 'https://[bad'):
            with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={'Location': location}))) as client:
                with self.assertRaises(click.ClickException):
                    with media_response(client, 'https://example.test/start'):
                        pass
        calls = []
        def safe(request):
            calls.append(request)
            return httpx.Response(302, headers={'Location': '/finish'}) if request.url.path == '/start' else httpx.Response(200, content=b'image')
        with httpx.Client(transport=httpx.MockTransport(safe)) as client:
            with media_response(client, 'https://example.test/start') as response:
                self.assertEqual(response.read(), b'image')
        self.assertEqual(len(calls), 2)
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={'Location': str(r.url)+'x'}))) as client:
            with self.assertRaises(click.ClickException):
                with media_response(client, 'https://example.test/start'):
                    pass
