import socket
import ipaddress
import os
import ssl
from unittest.mock import patch
import click
import httpx
from dotenv_support import IsolatedEnvironmentTestCase
from kulturbytes_common.media_security import validate_media_url, media_response, create_media_client

from kulturbytes_common.network import MediaPolicy
POLICY = MediaPolicy(allowed_hosts=['api.kulturbytes.de'])

REAL_MEDIA_CLIENT = create_media_client


class MediaSecurityTests(IsolatedEnvironmentTestCase):
    def test_nonpublic_literals_and_credentials_rejected(self):
        bad = ['localhost', '127.0.0.1', '10.0.0.1', '192.168.1.1', '172.16.0.1', '169.254.169.254',
               '0.0.0.0', '224.0.0.1', '192.0.2.1', '[::1]', '[::]', '[fc00::1]', '[fe80::1]',
               '[ff02::1]', '[::ffff:127.0.0.1]', 'user:password@example.test']
        for host in bad:
            with self.subTest(host=host), self.assertRaises(click.ClickException):
                validate_media_url('https://'+host+'/image.jpg', POLICY)
        for url in ('http://example.test/image', 'file:///image', 'https://example.test:bad/image'):
            with self.assertRaises(click.ClickException):
                validate_media_url(url, POLICY)
        with self.assertRaises(click.ClickException):
            validate_media_url('https://8.8.8.8/image', POLICY)
        validate_media_url('https://api.kulturbytes.de/image', POLICY)

    def test_dns_mixed_private_and_recheck_each_retry(self):
        def records(*ips):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in ips]
        for ips in [('10.0.0.1',), ('8.8.8.8', '127.0.0.1')]:
            with patch('socket.getaddrinfo', return_value=records(*ips)), self.assertRaises(click.ClickException):
                validate_media_url('https://api.kulturbytes.de/image', POLICY)
        calls = []
        with patch('socket.getaddrinfo', side_effect=[records('8.8.8.8'), records('127.0.0.1')]), \
             httpx.Client(transport=httpx.MockTransport(lambda r: (calls.append(r), httpx.Response(503))[1])) as client:
            with self.assertRaises(click.ClickException):
                with media_response(client, 'https://api.kulturbytes.de/image', POLICY):
                    pass
        self.assertEqual(len(calls), 1)

    def test_redirect_validation_and_limits(self):
        for location in ('https://127.0.0.1/image', '/start', '', 'https://user:pass@example.test/x', 'https://[bad'):
            with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={'Location': location}))) as client:
                with self.assertRaises(click.ClickException):
                    with media_response(client, 'https://api.kulturbytes.de/start', POLICY):
                        pass
        calls = []
        def safe(request):
            calls.append(request)
            return httpx.Response(302, headers={'Location': '/finish'}) if request.url.path == '/start' else httpx.Response(200, content=b'image')
        with httpx.Client(transport=httpx.MockTransport(safe)) as client:
            with media_response(client, 'https://api.kulturbytes.de/start', POLICY) as response:
                self.assertEqual(response.read(), b'image')
        self.assertEqual(len(calls), 2)
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={'Location': str(r.url)+'x'}))) as client:
            with self.assertRaises(click.ClickException):
                with media_response(client, 'https://api.kulturbytes.de/start', POLICY):
                    pass

    def test_rebinding_cannot_change_tcp_destination_and_proxies_are_ignored(self):
        # Exercise the real HTTPX/HTTPcore transport, replacing only the network backend.
        # A vulnerable hostname connection would resolve again and receive loopback.
        dns_calls, connections, tls_names, writes = [], [], [], []
        def resolver(host, port, **kwargs):
            dns_calls.append(host)
            address = '8.8.8.8' if len(dns_calls) == 1 else '127.0.0.1'
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, port))]
        test = self
        class Stream:
            def read(self, max_bytes, timeout=None):
                return b'HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\njpeg'
            def write(self, buffer, timeout=None):
                writes.append(buffer)
            def start_tls(self, ssl_context, server_hostname=None, timeout=None):
                test.assertTrue(ssl_context.check_hostname)
                test.assertEqual(ssl_context.verify_mode, ssl.CERT_REQUIRED)
                tls_names.append(server_hostname)
                return self
            def get_extra_info(self, info):
                return False if info == 'is_readable' else None
            def close(self):
                pass
        def connect_tcp(backend, host, port, **kwargs):
            try:
                actual = ipaddress.ip_address(host)
            except ValueError:
                actual = ipaddress.ip_address(socket.getaddrinfo(host, port)[0][4][0])
            connections.append(str(actual))
            test.assertTrue(actual.is_global, 'Rebinding reached a private TCP endpoint')
            return Stream()
        proxies = {name: 'http://proxy.attacker.test:8080' for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY')}
        with patch.dict(os.environ, proxies), patch('socket.getaddrinfo', side_effect=resolver), \
             patch('httpcore._backends.sync.SyncBackend.connect_tcp', new=connect_tcp), \
             patch('kulturbytes_common.media_security.create_media_client', side_effect=REAL_MEDIA_CLIENT), \
             httpx.Client(trust_env=False, headers={'Authorization': 'Bearer test-secret'}) as parent:
            with media_response(parent, 'https://api.kulturbytes.de/api/image/example', POLICY) as response:
                self.assertEqual(response.read(), b'jpeg')
                self.assertEqual(response.url.host, 'api.kulturbytes.de')
        self.assertEqual(dns_calls, ['api.kulturbytes.de'])
        self.assertEqual(connections, ['8.8.8.8'])
        self.assertEqual(tls_names, ['api.kulturbytes.de'])
        self.assertIn(b'host: api.kulturbytes.de', b''.join(writes).lower())
        self.assertNotIn(b'test-secret', b''.join(writes))

    def test_allowlist_rejects_external_hosts_ports_and_credential_variants(self):
        for url in ('https://attacker.example/image', 'https://api.kulturbytes.de.evil.test/image',
                    'https://api.kulturbytes.de:444/image', 'https://user:pass@api.kulturbytes.de/image',
                    'https://@api.kulturbytes.de/image'):
            with self.subTest(url=url), patch('socket.getaddrinfo') as resolver, self.assertRaises(click.ClickException):
                validate_media_url(url, POLICY)
            resolver.assert_not_called()
        for addresses in (['::1'], ['fc00::1'], ['8.8.8.8', 'fe80::1']):
            with patch('socket.getaddrinfo', return_value=[(socket.AF_INET6, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in addresses]):
                with self.assertRaises(click.ClickException):
                    validate_media_url('https://api.kulturbytes.de/image', POLICY)
