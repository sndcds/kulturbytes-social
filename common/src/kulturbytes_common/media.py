"""Source-neutral media downloads using private source policy."""

import httpx

from .image_urls import image_url
from .media_security import media_response
from .sources.models import ContentItem, RenderedPost


def post_image_url(post: ContentItem | RenderedPost, platform: str) -> str | None:
    if isinstance(post, RenderedPost):
        return post.image_url
    return image_url(
        post.image_url,
        post.media_policy.image,
        platform,
        post.image_width,
        post.image_height,
    )


def download_post_image(
    client: httpx.Client,
    post: ContentItem | RenderedPost,
    *,
    platform: str | None = None,
) -> tuple[bytes, str, str]:
    if not post.image_url:
        raise ValueError("Inhalt besitzt kein Bild")
    url = post.image_url
    if platform:
        url = post_image_url(post, platform)
    with media_response(client, url, post.media_policy) as response:
        response.read()
    content_type = (
        response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    )
    if content_type == "image/jpg":
        content_type = "image/jpeg"
    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(content_type, ".jpg")
    return response.content, content_type, (post.image_name or "image") + extension
