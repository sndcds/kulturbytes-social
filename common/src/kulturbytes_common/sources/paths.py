"""Checkout assets or installed XDG configuration followed by packaged defaults."""

import os
from pathlib import Path


def config_roots(kind: str) -> list[Path]:
    package = Path(__file__).resolve().parents[1]
    checkout = package.parents[2]
    if (checkout / "pyproject.toml").is_file() and (
        checkout / "common/src/kulturbytes_common"
    ).is_dir():
        return [checkout / kind]
    home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not home.is_absolute():
        home = Path.home() / ".config"
    return [home / "kulturbytes-social" / kind, package / "data" / kind]
