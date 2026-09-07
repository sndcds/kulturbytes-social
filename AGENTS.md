# AGENTS.md

## Purpose

This repository contains social publishing tools for **Kulturbytes**.

The primary goal is to publish Kulturbytes event data to external social platforms while keeping **Kulturbytes as the source of truth**.

Current targets:

- Facebook Pages
- Mastodon, especially `https://norden.social`

Agents working in this repository should preserve the same event-selection, enrichment, deduplication, preview, and publishing behavior across both publishers wherever possible.

This file distinguishes current implementation details from requirements for future changes. Known gaps below are not guarantees that the code already satisfies those requirements.

---

## Core principles

1. **Kulturbytes is the source of truth.**
   - Do not manually duplicate event data that is already available from the API.
   - Always derive social content from the Kulturbytes API.

2. **Use the event list only for discovery.**
   - Event overview:
     `https://api.kulturbytes.de/api/events`
   - Detailed event data:
     `https://api.kulturbytes.de/api/event/{uuid}/date/{date_slug}`

3. **Use `uuid` and `date_slug` for public links.**
   - Frontend URL format:
     `https://kulturbytes.de/de/veranstaltung/{uuid}/{date_slug}`

4. **Use `date_uuid` for deduplication.**
   - A recurring event can have multiple concrete dates.
   - Do not deduplicate only by event `uuid`.

5. **Default to safe operation.**
   - New publishing flows should support a dry-run mode.
   - Interactive publishing should require explicit confirmation.
   - Never bulk-publish large numbers of events accidentally.

6. **Use `httpx`.**
   - Do not introduce `requests`.

7. **Use `uv`.**
   - Dependency changes should be made with `uv add`, `uv remove`, or `uv sync`.
   - Keep `pyproject.toml` and `uv.lock` consistent.

8. **Use `click` for CLI interaction.**
   - Keep CLI behavior consistent between Facebook and Mastodon publishers.

---

## Supported API flow

### Event discovery

Fetch:

```text
GET https://api.kulturbytes.de/api/events
```

Use this endpoint for:

- listing upcoming events,
- filtering released events,
- interactive event selection,
- finding `uuid`,
- finding `date_uuid`,
- finding `date_slug`,
- sorting by date and time.

Do not use this endpoint as the final source for social publishing content when detailed event data is available.

### Event detail enrichment

For each selected event fetch:

```text
GET https://api.kulturbytes.de/api/event/{uuid}/date/{date_slug}
```

Use the returned `data` object as the canonical source for the social post.

The discovery response wraps the list in `data.events`; the detail response wraps one event in `data`. The field lists below describe possible fields, not a guaranteed schema. A live sample checked on 2026-09-07 omitted `tags`, `content_language`, `event_types`, and `event_links` from the detail response, and exposed `price_type` at event level. Several optional date fields were also absent. Handle missing fields gracefully; do not infer that missing tags mean the discovery record had no tags. Current formatting reads tags only from the detail object and prices only from `date`.

Important fields include:

```text
uuid
release_status
content_language
title
subtitle
description
summary
tags
org_uuid
org_name
org_web_link
images.main
event_types
event_links
date
```

Important fields inside `date` include:

```text
uuid
slug
event_uuid
release_status
start_date
start_time
end_date
venue_uuid
venue_name
venue_street
venue_house_number
venue_postal_code
venue_city
venue_country
venue_state
venue_lon
venue_lat
venue_web_link
price_type
min_price
max_price
currency
ticket_flags
ticket_link
```

---

## Event URL construction

Always construct the public frontend URL as:

```python
def get_event_url(event: dict) -> str:
    return (
        "https://kulturbytes.de/de/veranstaltung/"
        f"{event['uuid']}/"
        f"{event['date']['slug']}"
    )
```

Do not use:

```text
/events/{uuid}/{date_slug}
```

Do not use `date_uuid` in the public frontend URL.

---

## Event filtering

By default, only offer events that:

- have `release_status == "released"`,
- have a valid `start_date`,
- are today or in the future,
- have not already been published to the target platform.

Both publishers currently support:

- `--city Flensburg`: case-insensitive exact city match.
- `--limit N`: limit the offered list; default `50`, `0` means all candidates.
- `--include-published`: also offer known dates, with an additional confirmation even in dry run.

Current filtering checks the discovery record and requires `date_uuid`. It uses host-local `date.today()`, not explicitly Berlin time. Missing dates are skipped, but malformed dates can abort discovery. Detail-level release status is not rechecked; a mismatched detail date UUID only produces a warning. These are known gaps when improving validation.

Keep filtering logic consistent between platforms.

---

## Interactive selection

Use `click`.

The preferred interaction model is a numbered list such as:

```text
[  1] 07.09.2026 18:30 — Event title — Venue (Flensburg)
[  2] 11.09.2026 10:00 — Event title — Venue (Flensburg)
[  3] 12.09.2026 19:00 — Event title — Venue (Husum)
```

Supported selection syntax should include:

```text
2
1,4,7
3-6
1,3-5,9
all
alle
*
```

An empty selection exits without publishing.

In publish mode, ask for explicit confirmation before publishing each event.

Example:

```text
Diesen Termin jetzt auf Facebook veröffentlichen? [y/N]:
```

or:

```text
Diesen Termin jetzt auf Mastodon veröffentlichen? [y/N]:
```

---

## Dry-run behavior

Dry run should be the safe default for interactive commands.

Run from `facebook/` or `mastodon/` (there is no root `main.py`).
Both publishers require their access-token environment variables at import time, including for dry run and `--help`; Facebook also requires `FACEBOOK_PAGE_ID`. `.env` files are not loaded automatically.

CLI style:

```bash
uv run main.py
```

for dry run, and:

```bash
uv run main.py --publish
```

for actual publishing.

A dry run should:

- fetch the event details,
- build the final platform-specific content,
- show the image URL,
- show relevant metadata,
- not call the publishing endpoint,
- not write a successful publication record to SQLite.

---

## SQLite deduplication

The publishers use separate SQLite databases with incompatible platform-specific schemas. Do not point both at the same file. `DATABASE_PATH` overrides the path; relative paths resolve against the current working directory. Dry run may create the database and table but does not record publications.

Default names:

```text
facebook_posts.sqlite3
mastodon_posts.sqlite3
```

Use `date_uuid` as the primary key.

Facebook example:

```sql
CREATE TABLE IF NOT EXISTS published_events (
    date_uuid TEXT PRIMARY KEY,
    event_uuid TEXT NOT NULL,
    facebook_post_id TEXT NOT NULL,
    title TEXT NOT NULL,
    start_date TEXT NOT NULL,
    start_time TEXT,
    published_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

Mastodon example:

```sql
CREATE TABLE IF NOT EXISTS published_events (
    date_uuid TEXT PRIMARY KEY,
    event_uuid TEXT NOT NULL,
    mastodon_status_id TEXT NOT NULL,
    mastodon_status_url TEXT,
    title TEXT NOT NULL,
    start_date TEXT NOT NULL,
    start_time TEXT,
    published_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

Only write the publication record after the remote platform confirms success.

Known limitation: both writers use plain `INSERT`. Republishing with `--include-published` can succeed remotely and then fail locally with a duplicate primary key. It does not update the existing record. Do not describe this option as reliably recording repeat publications.

---

## Social hashtags

Use the detailed event field:

```python
event.get("tags") or []
```

Normalize every non-empty tag into a hashtag, discarding values that contain no usable characters. For Mastodon, all tags may not fit; preserve `#Kulturbytes` and the city where possible and remove optional tags only as whole hashtags when implementing length handling.

Always add:

```text
#Kulturbytes
```

Also add the venue city as a hashtag when available.

Example input:

```json
{
  "tags": [
    "Open Data",
    "Civic Tech",
    "GIS"
  ],
  "date": {
    "venue_city": "Flensburg"
  }
}
```

Expected result:

```text
#OpenData #CivicTech #GIS #Kulturbytes #Flensburg
```

Preserve Unicode characters where reasonable.

Remove:

- whitespace,
- hyphens,
- slashes,
- punctuation that is invalid or undesirable inside hashtags.

Avoid duplicate hashtags case-insensitively.

---

## Markdown handling

Kulturbytes descriptions can contain Markdown.

Examples:

```text
**Bold text**
```

```text
7\. September
```

```text
[Link text](https://example.org)
```

Do not publish raw Markdown to platforms that do not render it as expected.

Current implementation: `strip_markdown` exists only in the Mastodon CLI and handles a subset of Markdown. Facebook `build_message` currently passes Markdown through. Shared normalization for both platforms is a requirement for future formatting fixes, not existing behavior.

Typical transformations:

```text
**Text** -> Text
7\. September -> 7. September
[Website](https://example.org) -> Website: https://example.org
```

Do not modify the source data itself.

Only normalize the rendered social message.

---

# Facebook publisher

## Current publishing model

The Facebook publisher should publish a **Facebook Page post**, not attempt to create a Facebook Event unless Meta explicitly supports that operation for the configured app and API version.

Current preferred behavior:

1. If the event has a main image:
   - download it from Kulturbytes,
   - publish through the Facebook Photos endpoint,
   - use the social message as the image caption.

2. If the event has no main image:
   - publish a normal Page feed post.

### Image source

Use:

```python
event["images"]["main"]["url"]
```

when available.

Do not prefer the reduced `image_path` from `/api/events` after detailed event data has been loaded.

### Facebook photo publishing

Typical endpoint:

```text
POST /{PAGE_ID}/photos
```

The implementation should use `httpx`.

Expected environment variables:

```text
FACEBOOK_PAGE_ID
FACEBOOK_PAGE_ACCESS_TOKEN
FACEBOOK_GRAPH_API_VERSION
```

Do not hard-code access tokens.

### Facebook text fallback

Typical endpoint:

```text
POST /{PAGE_ID}/feed
```

The current code uses this endpoint only when `get_image_url` returns no URL. A failed image download or photo upload fails that event; there is no automatic text fallback.

### Facebook permissions

The configured Page Access Token may require permissions such as:

```text
pages_show_list
pages_read_engagement
pages_manage_posts
```

If Meta returns an authorization or permission error, report the API error payload after redacting secrets. Never print a raw payload or exception URL if it contains an access token.

### Facebook Event creation

Do not assume:

```text
POST /{PAGE_ID}/events
```

is available.

An earlier version of this document reported the following error, but the repository has no reproducible test establishing its cause:

```text
Unsupported post request
```

with Graph API error code `100` and subcode `33`.

This error alone does not establish which operation or permission is unsupported. Do not reintroduce Page Event creation without verifying current Meta Graph API support for the configured app and version.

`v26.0` is the current code default, not a claim about Meta’s latest supported version. The official [Page posts documentation](https://developers.facebook.com/docs/pages-api/posts/) could not be retrieved during the 2026-09-07 review (HTTP 429); current Meta support and permission requirements remain unverified.

---

# Mastodon publisher

## Target instance

Default target:

```text
https://norden.social
```

Allow overriding it with:

```text
MASTODON_BASE_URL
```

Expected environment variables:

```text
MASTODON_BASE_URL
MASTODON_ACCESS_TOKEN
```

Default:

```text
MASTODON_BASE_URL=https://norden.social
```

## Mastodon status publishing

Use:

```text
POST /api/v1/statuses
```

Use a Bearer token:

```http
Authorization: Bearer <token>
```

The user token needs `write:statuses` for posting and `write:media` for uploads (or encompassing scopes). See the official [status](https://docs.joinmastodon.org/methods/statuses/) and [media](https://docs.joinmastodon.org/methods/media/) API documentation.

Default visibility:

```text
public
```

## Mastodon media upload

If a main image exists:

1. Download the Kulturbytes event image.
2. Upload it to:

```text
POST /api/v2/media
```

3. Include alt text.
4. Wait until media processing is ready when necessary.
5. Attach the returned media ID to the status.

The API can return `200` for processed media or `202` while processing. Poll `GET /api/v1/media/{id}` until ready. Current `wait_for_media` checks up to ten times at one-second intervals, then only warns and continues; it does not raise on HTTP errors. Reliable failure/timeout handling remains to be implemented. See the [media API documentation](https://docs.joinmastodon.org/methods/media/).

Use the detailed image metadata:

```python
event["images"]["main"]
```

### Alt text

Prefer:

```python
event["images"]["main"]["alt"]
```

Fallback:

```text
Veranstaltungsbild zu {title}
```

Alt text should be useful and human-readable.

## Mastodon status length

Do not assume unlimited status text.

Current preview and publishing code use a hard-coded `max_length=500` and Python `len()`. They do not query the instance configuration.

A read-only check of `https://norden.social/api/v2/instance` on 2026-09-07 returned `configuration.statuses.max_characters = 500` and `characters_reserved_per_url = 23`. These values can change. For future limit handling, query `GET /api/v2/instance`, retain a 500-character fallback, and account for the instance's URL counting rules rather than assuming Python `len()` matches server validation. See the official [instance API](https://docs.joinmastodon.org/methods/instance/) and [configuration fields](https://docs.joinmastodon.org/entities/Instance/).

### Mastodon content strategy

Do not post the complete event description when it exceeds the platform limit.

Prefer:

```text
📅 Title
Subtitle
🗓 Date · Time
📍 Venue, City

Short summary…

👉 Kulturbytes URL
#Tags #Kulturbytes #City
```

Preserve enough room for:

- the Kulturbytes link,
- hashtags,
- date,
- venue,
- title.

Trim the summary first.

Never truncate the Kulturbytes URL.

Never truncate hashtags in the middle of a hashtag.

These are requirements for improved composition. The current final fallback uses `message[:max_length]`, which can cut off the Kulturbytes URL or hashtags when the fixed content is too long. It does not yet guarantee their preservation.

---

## Message composition

Platform-neutral event information is already shared through `kulturbytes_common`; final formatting remains in each platform CLI.

Existing shared helpers include:

```text
get_event_url
get_start_datetime
build_address
normalize_hashtag
build_hashtags
format_price
get_image_url
download_image
```

Existing platform-specific helpers include:

```text
build_message  # Facebook
build_mastodon_message
publish_facebook_photo
publish_text_post  # Facebook
strip_markdown  # currently Mastodon only
upload_mastodon_media
publish_mastodon_status
```

Do not force Facebook and Mastodon to use the exact same final message if platform constraints differ.

---

## Date and timezone handling

Use:

```text
Europe/Berlin
```

for Kulturbytes event times unless the API gains an explicit event timezone field.

Use Python's:

```python
from zoneinfo import ZoneInfo
```

Avoid naive datetimes when posting to APIs that require timestamps.

---

## Error handling

All external API calls should use:

```python
response.raise_for_status()
```

and report the response payload on failure after redacting secrets. This is a target requirement: current Kulturbytes/image requests do not print response bodies, media polling does not call `raise_for_status()`, and platform error helpers do not implement explicit secret redaction.

Good error output includes:

```text
platform
HTTP status
API error JSON or response body
event title
event uuid
date uuid
date slug
```

Never print:

- Facebook access tokens,
- Mastodon access tokens,
- other secrets.

A failed remote publication must not create a successful local deduplication record.

Errors on one manually selected event should generally not corrupt state for later events.

---

## HTTP client

Use a reusable `httpx.Client`.

Suggested timeout:

```python
httpx.Timeout(
    connect=10.0,
    read=60.0,
    write=60.0,
    pool=10.0,
)
```

Suggested options:

```python
follow_redirects=True
```

Set a meaningful `User-Agent`, for example:

```text
Kulturbytes-Facebook-Publisher/1.x
Kulturbytes-Mastodon-Publisher/1.x
```

---

## Secrets

Never commit secrets.

Do not commit:

```text
.env
.env.*
```

unless it is a deliberately tracked example file containing only non-secret defaults and empty credentials.

Do not commit:

```text
FACEBOOK_PAGE_ACCESS_TOKEN
MASTODON_ACCESS_TOKEN
```

Suggested `.gitignore` entries:

```gitignore
.venv/
.env
.env.*
!.env.example

*.sqlite
*.sqlite3
*.db

__pycache__/
*.py[cod]
```

---

## Example environment configuration

### Facebook

```env
FACEBOOK_PAGE_ID=
FACEBOOK_PAGE_ACCESS_TOKEN=
FACEBOOK_GRAPH_API_VERSION=v26.0
DATABASE_PATH=facebook_posts.sqlite3
```

### Mastodon

```env
MASTODON_BASE_URL=https://norden.social
MASTODON_ACCESS_TOKEN=
DATABASE_PATH=mastodon_posts.sqlite3
```

Do not include real secrets in `.env.example`. These snippets describe environment variables; creating an `.env` file alone does not configure the current programs.

---

## Dependency management

Use Python 3.12 or newer. The repository is a `uv` workspace with three packages and one root `uv.lock`. Add or remove dependencies in the package that uses them with `uv`.

Examples:

```bash
uv add --package kulturbytes-common httpx
uv add --package kulturbytes-common click
```

Run:

```bash
uv sync --all-packages
```

Execute scripts with:

```bash
uv run main.py
```

from the platform directory, or use `uv run --package kulturbytes-facebook kulturbytes-facebook` / `uv run --package kulturbytes-mastodon kulturbytes-mastodon` from the repository root.

Do not document `python -m venv` as the primary setup method for this repository.

---

## Code quality expectations

Agents should:

- use type hints,
- keep functions small and focused,
- avoid duplicated platform-neutral logic,
- preserve existing CLI behavior unless intentionally changing it,
- use descriptive function names,
- keep token handling out of logs,
- retain Unicode support,
- handle missing optional API fields gracefully,
- avoid hard-coded event IDs,
- avoid hard-coded publication state,
- keep API endpoints configurable where appropriate.

Before changing behavior, inspect the existing implementation rather than rewriting unrelated parts.

---

## Testing expectations

For publishing behavior changes, manually inspect dry-run output. Documentation-only edits require checking statements and commands against the code; they do not require live publishing.

Existing tests are in `tests/test_publishers.py`. Run from the repository root:

```bash
uv sync --all-packages
uv run --all-packages python -m unittest discover -s tests -v
```

They cover selection parsing, basic address/hashtag/price formatting, mocked image downloads, both dry-run CLIs, publication confirmation, SQLite records and duplicate filtering, and filtering/sorting/limits. Publication functions are mocked in the confirmed-publish test; this does not verify the actual platform HTTP requests.

Additional coverage is still needed for Markdown normalization, Mastodon link/hashtag preservation and instance limits, malformed dates, platform HTTP errors, media processing, and repeat-publication database behavior. Do not use live social publishing in automated tests.

---

## Current project structure

The shared implementation already exists as a `uv` workspace:

```text
pyproject.toml                 # workspace members
uv.lock                        # shared lockfile
common/src/kulturbytes_common/
    events.py                  # API reads, dates, URLs, hashtags, prices
    media.py                   # image URLs and downloads
    selection.py               # interactive selection
    database.py                # duplicate lookup
    workflow.py                # shared filtering and publishing loop
facebook/
    main.py                    # compatibility entry point
    src/kulturbytes_facebook/cli.py
mastodon/
    main.py                    # compatibility entry point
    src/kulturbytes_mastodon/cli.py
tests/test_publishers.py
```

Each platform CLI owns its configuration, final formatting, publication calls, and database schema/writer. Console commands are `kulturbytes-facebook` and `kulturbytes-mastodon`; there is no `kulturbytes-social` command. Keep the platform `main.py` wrappers functional. Do not introduce another architectural refactor unless requested.

---

## Definition of done

For publishing changes, verify the applicable requirements below and identify remaining known gaps explicitly. This checklist describes the target behavior, not a claim that every item already passes:

- the event list still loads,
- detailed event data is fetched correctly,
- the frontend URL is correct,
- future/released filtering still works,
- interactive selection works,
- already-published events are excluded by default,
- dry run produces the exact intended output,
- images are taken from detailed event data,
- hashtags include event tags, `#Kulturbytes`, and city,
- Markdown does not leak into platforms that do not render it,
- the target platform's text limit is respected,
- remote API failures do not mark events as published,
- secrets are not logged,
- SQLite deduplication remains correct,
- `uv sync --all-packages` and the existing test suite succeed.
