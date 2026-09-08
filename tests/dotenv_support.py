"""Every test gets a private .env, including existing authentication regressions."""
import tempfile
import socket
import unittest
from pathlib import Path
from unittest.mock import patch


class IsolatedEnvironmentTestCase(unittest.TestCase):
    def run(self, result=None):
        with patch('socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))]), patch('kulturbytes_common.http.time.sleep'), tempfile.TemporaryDirectory() as directory, patch(
            'kulturbytes_common.environment.get_env_file_path', return_value=Path(directory) / '.env',
        ):
            return super().run(result)
