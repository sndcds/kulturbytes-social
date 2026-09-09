"""Feed historical raw fixtures through the configured generic mapping engine."""

from kulturbytes_common.media import download_post_image
from kulturbytes_common.rendering import hashtags
from kulturbytes_common.sources.loader import load_source
from kulturbytes_common.sources.models import ContentItem, RenderedPost


def canonical(event):
    if isinstance(event, (ContentItem, RenderedPost)):
        return event
    detail = event["date"]
    listed = {
        "uuid": event["uuid"],
        "date_uuid": detail["uuid"],
        "date_slug": detail["slug"],
        "summary": event.get("summary"),
    }
    return load_source("kulturbytes").map_detail(event, listed=listed)


def get_event_url(event):
    return canonical(event).link


def build_address(event):
    return canonical(event).address


def format_price(event):
    return canonical(event).price


def build_hashtags(event):
    item = canonical(event)
    return hashtags(item.tags + ["Kulturbytes"], city=item.city)


def download_image(client, event):
    return download_post_image(client, canonical(event))
