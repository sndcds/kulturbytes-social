"""Single text/image posts using XRPC, without mutation retries."""

import base64
import binascii
import re
from datetime import datetime, timezone
from urllib.parse import quote

import click
import httpx

from kulturbytes_common.atproto_identity import post_identity
from kulturbytes_common.auth import redact
from kulturbytes_common.media import download_post_image
from kulturbytes_common.publications import begin_remote_mutation
from kulturbytes_common.sources.models import RenderedPost
from kulturbytes_common.text_limits import bluesky_text_fits

from .auth import Session, xrpc

IMAGE_MAX_BYTES = 2_000_000


def valid_cid(value: object) -> bool:
    # AT Protocol uses CIDv1 with SHA-256 (raw blobs or DAG-CBOR records).
    if not isinstance(value, str) or not re.fullmatch(r"b[a-z2-7]{58}", value):
        return False
    try:
        data = base64.b32decode(value[1:].upper() + "=" * (-len(value[1:]) % 8))
    except (ValueError, binascii.Error):
        return False
    return len(data) == 36 and data[:4] in (b"\x01\x55\x12\x20", b"\x01\x71\x12\x20")


def link_facets(text: str) -> list[dict]:
    facets = []
    for match in re.finditer(r"https?://[^\s<>]+", text):
        url = match[0].rstrip(".,!?;:")
        start = len(text[: match.start()].encode("utf-8"))
        end = start + len(url.encode("utf-8"))
        if start < end:
            facets.append(
                {
                    "index": {"byteStart": start, "byteEnd": end},
                    "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
                }
            )
    return facets


def image_mime(content: bytes, declared: str) -> str:
    if content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9"):
        actual = "image/jpeg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        actual = "image/png"
    elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        actual = "image/webp"
    else:
        raise click.ClickException(
            "Bluesky: Bild benötigt JPEG-, PNG- oder WebP-Dateisignatur."
        )
    if declared != actual:
        raise click.ClickException(
            "Bluesky: Bildinhalt und MIME-Typ stimmen nicht überein."
        )
    return actual


def upload_image(client: httpx.Client, session: Session, post: RenderedPost) -> dict:
    content, mime, _ = download_post_image(
        client, post, platform="bluesky", max_bytes=IMAGE_MAX_BYTES
    )
    if not content or len(content) > IMAGE_MAX_BYTES:
        raise click.ClickException(
            "Bluesky: Bild ist leer oder überschreitet 2000000 Bytes."
        )
    mime = image_mime(content, mime)
    begin_remote_mutation("bluesky_blob")
    payload = xrpc(
        client,
        session.service_url,
        "com.atproto.repo.uploadBlob",
        token=session.access_jwt,
        content=content,
        headers={"Content-Type": mime},
    )
    blob = payload.get("blob")
    if (
        not isinstance(blob, dict)
        or blob.get("$type") != "blob"
        or not isinstance(blob.get("ref"), dict)
        or not valid_cid(blob["ref"].get("$link"))
        or blob.get("mimeType") != mime
        or type(blob.get("size")) is not int
        or blob["size"] != len(content)
    ):
        raise click.ClickException(
            "Bluesky: ungültige Blob-Antwort; kein Post erstellt."
        )
    # Keep only validated fields so arbitrary response metadata cannot enter the record.
    return {
        "$type": "blob",
        "ref": {"$link": blob["ref"]["$link"]},
        "mimeType": mime,
        "size": blob["size"],
    }


def publish_post(
    client: httpx.Client, session: Session, post: RenderedPost
) -> tuple[str, str]:
    if not bluesky_text_fits(post.text):
        raise click.ClickException(
            "Bluesky: maximal 300 Grapheme und 3000 UTF-8-Bytes erlaubt."
        )
    record = {
        "$type": "app.bsky.feed.post",
        "text": post.text,
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    facets = link_facets(post.text)
    if facets:
        record["facets"] = facets
    if post.image_url:
        record["embed"] = {
            "$type": "app.bsky.embed.images",
            "images": [
                {
                    "alt": post.image_alt or "",
                    "image": upload_image(client, session, post),
                }
            ],
        }
    begin_remote_mutation("bluesky_post")
    payload = xrpc(
        client,
        session.service_url,
        "com.atproto.repo.createRecord",
        token=session.access_jwt,
        json={
            "repo": session.did,
            "collection": "app.bsky.feed.post",
            "record": record,
        },
    )
    uri = payload.get("uri")
    identity = post_identity(uri)
    if (
        not identity
        or identity[0] != session.did
        or not valid_cid(payload.get("cid"))
        or any(
            redact(uri, secret) != uri
            for secret in (session.access_jwt, *session.secrets)
        )
    ):
        raise click.ClickException(
            "Bluesky: ungültige Post-URI/CID; Ergebnis manuell prüfen."
        )
    return (
        uri,
        f"https://bsky.app/profile/{session.handle}/post/{quote(identity[1], safe='')}",
    )
