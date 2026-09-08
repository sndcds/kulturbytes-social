"""Every test gets a private .env, including existing authentication regressions."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class IsolatedEnvironmentTestCase(unittest.TestCase):
    def run(self, result=None):
        with tempfile.TemporaryDirectory() as directory, patch(
            'kulturbytes_common.environment.get_env_file_path', return_value=Path(directory) / '.env',
        ):
            return super().run(result)
