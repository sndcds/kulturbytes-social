"""Every test gets a private .env, including existing authentication regressions."""
import tempfile
import socket
import unittest
import httpx
from kulturbytes_common.media_security import PublicMediaTransport

HTTPXClient = httpx.Client

def mock_media_client(parent):
    # Keep the real pinning policy, then adapt the numeric request for existing API fixtures.
    def endpoint(request):
        logical = httpx.Request(request.method, request.url.copy_with(host=request.extensions["sni_hostname"]),
                                headers=request.headers, extensions=request.extensions)
        return parent.send(logical, stream=True, follow_redirects=False)
    return HTTPXClient(transport=PublicMediaTransport(httpx.MockTransport(endpoint)),
                       timeout=parent.timeout, trust_env=False)
from pathlib import Path
from unittest.mock import patch


class IsolatedEnvironmentTestCase(unittest.TestCase):
    def run(self, result=None):
        with patch('kulturbytes_common.media_security.create_media_client', side_effect=mock_media_client), patch('socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))]), patch('kulturbytes_common.http.time.sleep'), tempfile.TemporaryDirectory() as directory, patch(
            'kulturbytes_common.environment.get_env_file_path', return_value=Path(directory) / '.env',
        ):
            return super().run(result)
