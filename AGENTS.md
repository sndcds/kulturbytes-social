# AGENTS.md

## Purpose

This repository contains social publishing tools for **Kulturbytes**.

The primary goal is to publish Kulturbytes event data to external social platforms while keeping **Kulturbytes as the source of truth**.

Current targets:

- Facebook Pages
- Mastodon, especially `https://norden.social`

Agents working in this repository should preserve the same event-selection, enrichment, deduplication, preview, and publishing behavior across both publishers wherever possible.

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

Optional CLI filters may include:

- `--city Flensburg`
- `--limit N`
- `--include-published`

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
```

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

Preferred CLI style:

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

Use a separate SQLite database per target platform unless the codebase intentionally introduces a shared publishing database.

Suggested names:

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

---

## Social hashtags

Use the detailed event field:

```python
event.get("tags") or []
```

Convert every tag into a hashtag.

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

Provide a normalization helper for social text.

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

Use only when no usable event image is available.

### Facebook permissions

The configured Page Access Token may require permissions such as:

```text
pages_show_list
pages_read_engagement
pages_manage_posts
```

If Meta returns an authorization or permission error, print the complete API error payload without exposing the access token.

### Facebook Event creation

Do not assume:

```text
POST /{PAGE_ID}/events
```

is available.

Previous testing showed that this operation can return:

```text
Unsupported post request
```

with Graph API error code `100` and subcode `33`.

Do not reintroduce Page Event creation without verifying current Meta Graph API support.

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

`norden.social` currently rejects posts above its configured character limit.

A previously observed response was:

```text
422 Unprocessable Content
Gültigkeitsprüfung ist fehlgeschlagen:
Text Begrenzung von 500 Zeichen überschritten
```

Therefore Mastodon publishing must enforce the instance's character limit before posting.

At minimum support a 500-character fallback limit.

Prefer querying instance configuration when practical instead of permanently assuming 500 characters.

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

---

## Message composition

Platform-neutral event information can be shared through helper functions, but final formatting should remain platform-specific.

Useful shared helpers include:

```text
get_event_url
get_start_datetime
build_address
normalize_hashtag
build_hashtags
format_price
get_image_url
download_image
strip_markdown
```

Platform-specific helpers should include:

```text
build_facebook_message
build_mastodon_message
publish_facebook_photo
publish_facebook_text
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

but print the platform's response payload first when a request fails.

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

unless an intentionally empty example file is used.

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

Do not include real secrets in `.env.example`.

---

## Dependency management

Add dependencies with `uv`.

Examples:

```bash
uv add httpx
uv add click
```

Run:

```bash
uv sync
```

Execute scripts with:

```bash
uv run main.py
```

or the appropriate platform-specific entry point.

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

At minimum, changes should be manually tested in dry-run mode.

Recommended future automated tests:

- hashtag normalization,
- duplicate hashtag removal,
- event URL generation,
- date formatting,
- price formatting,
- Markdown stripping,
- Mastodon length trimming,
- event selection parsing,
- SQLite deduplication,
- missing image fallback,
- mocked Facebook API publishing,
- mocked Mastodon media publishing,
- mocked Mastodon status publishing.

Do not use live social publishing in automated tests.

---

## Recommended project structure

A future shared implementation may use:

```text
src/
└── kulturbytes_social/
    ├── __init__.py
    ├── api.py
    ├── cli.py
    ├── database.py
    ├── formatting.py
    ├── facebook.py
    └── mastodon.py
```

Possible command layout:

```text
kulturbytes-social facebook
kulturbytes-social mastodon
```

Do not perform this refactor automatically unless requested.

Existing standalone scripts are valid and should remain functional until a shared architecture is deliberately introduced.

---

## Definition of done

A publishing change is done when:

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
- `uv sync` succeeds.
