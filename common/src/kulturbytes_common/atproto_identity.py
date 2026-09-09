"""Bounded AT Protocol identities shared with credential-free journal recovery."""

import re

DID_PATTERN = r"did:[a-z]+:[A-Za-z0-9._:%-]+"
AT_POST_PATTERN = (
    rf"at://({DID_PATTERN})/app\.bsky\.feed\.post/([A-Za-z0-9._~:-]{{1,512}})"
)


def valid_did(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 200
        and bool(re.fullmatch(DID_PATTERN, value))
    )


def post_identity(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str) or len(value) > 800:
        return None
    match = re.fullmatch(AT_POST_PATTERN, value)
    if not match or not valid_did(match[1]) or match[2] in (".", ".."):
        return None
    return match[1], match[2]
