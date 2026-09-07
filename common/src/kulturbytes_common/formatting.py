"""Normalization of social text without modifying API data."""

import re


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
