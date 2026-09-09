"""Adapt existing raw Kulturbytes fixtures at the source boundary in unit tests."""

from kulturbytes_common.sources.kulturbytes import from_kulturbytes
from kulturbytes_common.sources.models import RenderedPost, ContentItem


def canonical(event):
    return (
        event
        if isinstance(event, (ContentItem, RenderedPost))
        else from_kulturbytes(event)
    )
