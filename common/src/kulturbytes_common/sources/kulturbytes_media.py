"""Legacy raw-image helper used only at the bundled source boundary."""

import httpx


def get_image_url(item: dict) -> str | None:
    return ((item.get("images") or {}).get("main") or {}).get("url")


def download_image(client: httpx.Client, item: dict):
    from ..media import download_post_image
    from .kulturbytes import from_kulturbytes

    return download_post_image(client, from_kulturbytes(item))
