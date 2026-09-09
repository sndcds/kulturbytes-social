"""Every test gets a private .env, including existing authentication regressions."""
import tempfile
import socket
import unittest
import httpx
from contextlib import contextmanager
from unittest.mock import Mock
from kulturbytes_common.sources.fetching import source_client as real_source_client
from kulturbytes_common.media_security import PublicMediaTransport

HTTPXClient = httpx.Client

def mock_media_client(parent, policy):
    # Keep the real pinning policy, then adapt the numeric request for existing API fixtures.
    def endpoint(request):
        logical = httpx.Request(request.method, request.url.copy_with(host=request.extensions["sni_hostname"]),
                                headers=request.headers, extensions=request.extensions)
        return parent.send(logical, stream=True, follow_redirects=False)
    return HTTPXClient(transport=PublicMediaTransport(policy, httpx.MockTransport(endpoint)),
                       timeout=parent.timeout, trust_env=False)
from pathlib import Path
from unittest.mock import patch


@contextmanager
def fixture_source_client():
    # Older platform fixtures inject one borrowed client into the workflow.
    # Generic source tests install their own factory, exercising isolated clients.
    if isinstance(httpx.Client, Mock):
        yield httpx.Client(trust_env=False, follow_redirects=False)
    else:
        with real_source_client() as client:
            yield client


class IsolatedEnvironmentTestCase(unittest.TestCase):
    def run(self, result=None):
        with patch('kulturbytes_common.sources.fetching.source_client', side_effect=fixture_source_client), patch('kulturbytes_common.media_security.create_media_client', side_effect=mock_media_client), patch('socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))]), patch('kulturbytes_common.http.time.sleep'), tempfile.TemporaryDirectory() as directory, patch(
            'kulturbytes_common.environment.get_env_file_path', return_value=Path(directory) / '.env',
        ):
            return super().run(result)
