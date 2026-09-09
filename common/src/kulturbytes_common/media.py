"""Source-neutral media downloads using private source policy."""

import httpx

from .media_security import media_response
from .sources.models import ContentItem, RenderedPost


def download_post_image(
    client: httpx.Client, post: ContentItem | RenderedPost
) -> tuple[bytes, str, str]:
    if not post.image_url:
        raise ValueError("Inhalt besitzt kein Bild")
    with media_response(client, post.image_url, post.media_policy) as response:
        response.read()
    content_type = (
        response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    )
    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(content_type, ".jpg")
    return response.content, content_type, (post.image_name or "image") + extension
