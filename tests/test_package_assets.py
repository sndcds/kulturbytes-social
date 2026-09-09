"""Build/install a real common wheel and resolve assets outside the checkout."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv_support import IsolatedEnvironmentTestCase


class PackageAssetTests(IsolatedEnvironmentTestCase):
    def test_installed_wheel_assets_and_cwd_independence(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(
                [
                    "uv",
                    "build",
                    "--package",
                    "kulturbytes-common",
                    "--out-dir",
                    str(root / "dist"),
                ],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            wheel = next((root / "dist").glob("*.whl"))
            subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--no-deps",
                    "--target",
                    str(root / "installed"),
                    str(wheel),
                ],
                check=True,
                capture_output=True,
            )
            script = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import kulturbytes_common
assert Path(kulturbytes_common.__file__).is_relative_to(Path(sys.argv[1]))
from kulturbytes_common.sources.loader import definitions
from kulturbytes_common.sources.models import ContentItem
from kulturbytes_common.rendering import TemplateRenderer
assert set(definitions()) == {'kulturbytes','example-simple','example-nested','example-events','example-places','example-articles'}
for platform in ('facebook','instagram','mastodon'):
    assert TemplateRenderer().render(ContentItem(title='Installed'),platform).text == 'Installed'
print('installed assets OK')
"""
            result = subprocess.run(
                [sys.executable, "-I", "-c", script, str(root / "installed")],
                cwd=root,
                env={**os.environ, "XDG_CONFIG_HOME": str(root / "config")},
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("installed assets OK", result.stdout)
