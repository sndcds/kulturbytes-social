"""Normalization of social text without modifying API data."""

import re
import unicodedata


def strip_markdown(text: str) -> str:
    if not text:
        return ""

    # Markdown-Links: [Text](URL) -> Text: URL
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r"\1: \2",
        text,
    )

    # Bold / italic
    text = re.sub(
        r"\*\*(.*?)\*\*",
        r"\1",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"__(.*?)__",
        r"\1",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"(?<!\*)\*([^*]+)\*(?!\*)",
        r"\1",
        text,
    )

    # Escaped Markdown-Zeichen
    text = re.sub(
        r"\\([\\`*_{}\[\]()#+\-.!])",
        r"\1",
        text,
    )

    # Mehr als zwei Leerzeilen reduzieren
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


def normalize_hashtag(
    value: str,
) -> str | None:
    if not value:
        return None

    value = value.strip()

    if not value:
        return None

    value = unicodedata.normalize(
        "NFC",
        value,
    )

    value = re.sub(
        r"[\s\-_/]+",
        "",
        value,
    )

    value = re.sub(
        r"[^\wÄÖÜäöüß]",
        "",
        value,
        flags=re.UNICODE,
    )

    if not value:
        return None

    return f"#{value}"
