"""Unicode-safe Bluesky text constraints from app.bsky.feed.post."""

import regex

BLUESKY_GRAPHEMES = 300
BLUESKY_BYTES = 3000


def grapheme_count(text: str) -> int:
    return len(regex.findall(r"\X", text))


def bluesky_text_fits(text: str) -> bool:
    try:
        return (
            len(text.encode("utf-8")) <= BLUESKY_BYTES
            and grapheme_count(text) <= BLUESKY_GRAPHEMES
        )
    except UnicodeError:
        return False


def grapheme_words(text: str) -> list[str]:
    """Split at whitespace clusters, never inside a combining/ZWJ sequence."""
    words = []
    current = []
    for cluster in regex.findall(r"\X", text):
        if cluster.isspace():
            if current:
                words.append("".join(current))
                current = []
        else:
            current.append(cluster)
    if current:
        words.append("".join(current))
    return words
