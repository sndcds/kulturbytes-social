# AGENTS.md

## Purpose

This repository contains social publishing tools for **Kulturbytes**.

The primary goal is to publish Kulturbytes event data to external social platforms while keeping **Kulturbytes as the source of truth**.

Current targets:

- Facebook Pages
- Instagram professional accounts (single-image feed posts)
- Mastodon, especially `https://norden.social`

Agents working in this repository should preserve the same event-selection, enrichment, deduplication, preview, and publishing behavior across all publishers wherever possible.

This file distinguishes current implementation details from requirements for future changes. Known gaps below are not guarantees that the code already satisfies those requirements.

---

## Source and presentation boundaries

Kulturbytes remains the default source. Configured JSON collections are also supported.
The Kulturbytes-specific API rules below apply inside its adapter, not to generic sources.

- Source-specific JSON property names must stay inside source adapters/mappings
  and the existing Kulturbytes boundary helpers they call.
- All source data must become `SocialItem` before rendering. Its only required
  content field is `title`; publishing additionally requires a stable `id`.
- JMESPath is the supported extraction language. Define generic sources in
  `sources/*.yaml`; do not add publisher fallback chains such as `title or name or headline`.
- Jinja2 is the supported presentation system. Use the central `TemplateRenderer`
  and `templates/<source>/<platform>.j2`, falling back to `templates/default/`.
- Publishers operate only on `SocialItem`/`RenderedPost` and explicit platform config.
  Do not read raw JSON paths or instantiate per-publisher Jinja environments.
- Keep the sandbox restricted to canonical fields and registered safe filters.
  Templates are trusted admin configuration; content is never executable template code.
- Keep platform limits outside arbitrary template control. Re-render shortened
  content fields; never slice the complete post or truncate protected links/hashtags.
- Generic source HTTP uses a separate client with no social credentials or inherited
  authenticated state. Mapped image URLs still pass the existing media SSRF path.
- Root `sources/` and `templates/` are symlinks to common package data. Preserve
  wheel/sdist inclusion and test installed access outside the checkout. Use deterministic
  checkout paths or installed XDG configuration; never discover configuration from CWD.
- `sources list` and `sources validate SOURCE` are local, read-only commands.
- Keep Kulturbytes date IDs and recovery snapshots compatible. Generic publication
  keys are `<source>:<id>`; old journal column names are internal storage details,
  not public canonical fields. Do not change the persistence architecture for source work.
- Preserve the captured Kulturbytes output fixtures in `tests/fixtures/` and run
  mapping, sandbox, generic CLI and installed-package tests alongside existing tests.

---

## Core principles

1. **Kulturbytes is the source of truth.**
   - Do not manually duplicate event data that is already available from the API.
   - Always derive social content from the Kulturbytes API.

2. **Use the event list for discovery and the social summary.**
   - Event overview:
     `https://api.kulturbytes.de/api/events`
   - Detailed event data:
     `https://api.kulturbytes.de/api/event/{uuid}/date/{date_slug}`
   - Prefer the selected list record's non-empty `summary` for social text; otherwise use `description` from the detail response. Whitespace-only summaries count as empty. Do not fall back to the detail response's `summary`.

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
   - Keep CLI behavior consistent between the platform publishers.

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

Use this endpoint's `summary` as the preferred social body text for all publishers. Always fetch the selected event's details for the remaining content and metadata, and use their `description` when the list summary is missing or empty.

### Event detail enrichment

For each selected event fetch:

```text
GET https://api.kulturbytes.de/api/event/{uuid}/date/{date_slug}
```

Use the returned `data` object as the canonical source for event metadata and the fallback `description`. The Kulturbytes adapter creates a copy with `summary` set from the selected list record (or an empty string), then maps it into canonical `text` using list summary first and detail description second without modifying the API response objects. Mastodon still applies its platform-specific normalization and length limit.

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

All publishers currently support:

- `--city Flensburg`: case-insensitive exact city match.
- `--limit N`: limit the offered list; default `50`, `0` means all candidates.
- `--include-published`: also offer known dates, with an additional confirmation even in dry run.

Current filtering checks validated discovery records and requires `date_uuid`. It uses the shared `application_today()` in Europe/Berlin. Invalid/missing dates are rejected at the API boundary per list item; malformed envelopes fail. Detail-level release status is not rechecked.

The summary `date_uuid` and detailed `date.uuid` must match. A mismatched or missing detailed date identity is a hard error before `publish_event`, including in dry run: no remote publication or local publication-record update is allowed, and the summary identifier must not be substituted. Errors include the event UUID, date slug, and both date identifiers. Direct selection exits nonzero; interactive selection reports the error for that event and continues with remaining selected events.

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

## Direct event selection

All CLIs accept `--event-uuid UUID --date-identifier IDENTIFIER` together.
`IDENTIFIER` may be a `date_slug` or `date_uuid`. Resolve the pair against
`/api/events` before applying the list limit, require exactly one match, and fetch
its details using the resolved slug. Preserve the list-summary/detail-description
text strategy. Skip numbered selection, but keep dry-run default, publication
confirmation, and release/date/city/deduplication filters. Unmatched, ambiguous,
or filtered targets and direct publication failures return a nonzero exit code.
`--include-published` retains its additional confirmation and replaces the stored publication after remote success.

---

## Dry-run behavior

Dry run should be the safe default for interactive commands.

There is exactly one primary public CLI: `kulturbytes-social`. Run `uv run kulturbytes-social PLATFORM ...` from the repository root, or the installed command from any directory. Platform packages expose reusable named Click command objects; they have no public scripts or main.py wrappers. New publishers must be subcommands (for example `kulturbytes-social bluesky`), never separate executables.
All three publishers load social credentials lazily through `load_config()` and frozen configuration dataclasses whose token fields use `repr=False`. Imports, dry run, and `--help` work without credentials. `--publish` validates required credentials before event discovery or database initialization. Authentication/configuration reads the deterministic `.env` first for every platform.

CLI style:

```bash
uv run kulturbytes-social facebook
```

for dry run, and:

```bash
uv run kulturbytes-social facebook --publish
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

## Authentication preflight

All platform subcommands support `--check-auth`, e.g. `uv run kulturbytes-social facebook --check-auth`.
It takes precedence over `--publish`, `--dry-run`, and event-selection options;
no event discovery, image reads/uploads, media containers, remote content
creation, or database access may occur. Missing/invalid configuration or failed
account validation exits nonzero; success displays the page/account name and exits 0.
For example, success displays `✓ Facebook Token gültig`; an expired Meta token
(code 190, subcode 463) reports `Facebook Access Token ist abgelaufen.`

- Facebook: GET the configured version/page ID with `fields=id,name`; require the returned ID to match and a non-empty name.
- Mastodon: GET `/api/v1/accounts/verify_credentials`; require account ID and acct/username.
- Instagram: GET the configured version/user ID with `fields=id,username`, using the existing login-mode host; require matching ID and non-empty username.
- Validate numeric Meta IDs, Graph version format, Instagram login type, and an HTTP(S) Mastodon origin without embedded credentials, path, query, or fragment.
- Use Bearer headers, no redirects or retries, and shared redaction from `kulturbytes_common.auth`. Never display tokens, including API-echoed values and encoded forms. Transport failures must not print raw exception text.
- This read-only check validates account access, not all publishing permissions. Do not add token refresh or OAuth flows; validated primary Meta credentials are persisted centrally to `.env`; keyring management remains explicit. Facebook may prompt for recovery only in a TTY.

## No platform-specific credential precedence

Platform packages must not implement special-case credential precedence. All credentials
use `resolve_credential_source`; Mastodon is not an exception. Non-secret settings with
.env support use shared `get_config`, never direct `os.getenv` in platform code.
`MASTODON_ACCESS_TOKEN` follows .env > environment > keyring with identical empty-value
semantics. `MASTODON_BASE_URL` follows .env > environment > `https://norden.social`,
retaining existing strict origin validation and trailing slash normalization.
Mastodon does not bootstrap or persist credentials automatically. Dry runs only read
non-secret instance configuration and never request credentials or touch keyring.
Mastodon publishing resolves one config for the invocation and passes it through media
upload, polling and status publication. Instance-limit discovery uses that same base URL.

## Central authentication configuration and local `.env`

Authentication configuration is resolved centrally in `kulturbytes_common.environment`
and `credentials`. For local use, the deterministic `.env` is the primary persistent
source. Platform packages must not implement separate parsing or persistence.
Facebook and Instagram share `META_SYSTEM_USER_ACCESS_TOKEN`; derived platform
credentials remain ephemeral unless explicitly required by the isolated legacy flow.

Source checkout: `<repo>/.env`, located from the common module, never from CWD.
Installed packages: absolute `$XDG_CONFIG_HOME/kulturbytes-social/.env`, otherwise
`~/.config/kulturbytes-social/.env`. Relative XDG values are ignored. No whole-process
`load_dotenv` mutation: use explicit lookup. python-dotenv parses literal values without
interpolation. Meta IDs, login mode and Graph versions also read .env before environment.
Mastodon uses the same shared credential resolver and `get_config` for its base URL.
Database-path configuration is unchanged.

Non-empty `.env` credentials win over environment and keyring. Empty `.env` credentials
permit fallback; explicit empty environment credentials still suppress their keyring
lookup. Blank non-secret .env settings override lower sources and fail validation where
required. Shared-source failures never trigger retries with legacy credentials.
When no shared or legacy credential exists, authentication may prompt for a Meta System
User Token with `hide_input=True` only if stdin/stdout are TTYs. No non-TTY prompts.
No auth/bootstrap/file writes during help/imports/dry runs.

After successful exact target validation, persist a primary Meta candidate from
Environment, keyring or prompt to .env and keep using the validated in-memory value.
Never persist before validation; never relabel legacy Page/User/Instagram tokens as
System User tokens. Never persist derived Page tokens in .env. Validation failures leave
file bytes, keyring and publication state unchanged. Persistence failure stops publication.
`--check-auth` may bootstrap .env but never performs event/image/content/publication-DB work.

The writer preserves unrelated bindings, comments and blank lines, replaces/deduplicates
only the requested key, fsyncs a same-directory temporary file and atomically replaces
the target with cleanup on error. POSIX files use 0600; validated existing files are
also tightened. Reject symlinks/invalid files and sanitize IO errors. Never commit `.env`.
Only `.env.example` with empty credentials is tracked. Status reports presence/source,
never token values. Existing keyring set/delete remain explicit keyring operations;
neither changes a .env entry already adopted by successful authentication.

Tests must use temporary .env paths (including existing auth tests), mocked keyring
and mocked HTTP. `tests/dotenv_support.py` isolates each test from the operator's file.

## Optional OS-keyring credentials

`kulturbytes_common.credentials` owns keyring lookup, storage, deletion, and the shared
Click management options. Python `keyring` is a dependency of `kulturbytes-common`,
added through `uv add --package kulturbytes-common keyring`; keep the root lockfile synced.
Never call `secret-tool` from application code or implement custom encryption.

All credentials resolve .env > environment > OS keyring. Meta additionally supports
hidden TTY bootstrap; Mastodon retains its missing-credential error. Even an explicitly empty environment
variable suppresses keyring access; whitespace-only values count as missing. Generic
lookup never prompts. Help/imports/dry runs must not touch the keyring. Config loaders
and auth checks use the same resolver.

Facebook and Instagram prefer `META_SYSTEM_USER_ACCESS_TOKEN` from `.env`, then
process environment, then the single shared OS-keyring entry. Only absence (including an explicitly empty shared
environment override) or an unavailable optional shared keyring permits legacy
credential lookup. Invalid shared credentials or incompatible login configuration
must fail closed, never trigger a legacy retry. Environment-only operation works
without an OS keyring.

Facebook resolves the exact page using the existing safely paginated `/me/accounts`
lookup and validates the derived Page Token against `FACEBOOK_PAGE_ID`. Shared-token
operation never prompts for repair or persists derived Page Tokens; use them only
in memory for the current invocation. Instagram uses the System User token directly
on `graph.facebook.com`; its default login is `facebook` when the shared token is
present. Explicit `INSTAGRAM_LOGIN_TYPE=instagram` with a shared token is rejected
before network access. Both publishers validate their configured target before
opening publication databases, loading events/images, or creating remote content.

The Meta System User must already have the required Business Portfolio/app/Page/
linked Instagram Professional Account access and permissions. No browser OAuth,
token refresh, automatic migration, System User creation or asset provisioning.

Legacy compatibility remains for this transition release, with a concise deprecation
warning and removal only in a separately announced breaking release. Old Facebook
Page/User env/keyring credentials retain the PR #17 recovery behavior, isolated in
`authenticate_legacy_page`. Only that path offers TTY recovery and separately confirmed
Page Token storage. The deprecated `--resolve-page-token` works for legacy recovery;
with a shared token it performs the same read-only validation as `--check-auth`.
Old Instagram credentials retain their default `instagram` login and explicit `facebook`
mode. No existing keyring entry is automatically overwritten or deleted.

Stable mappings (both Meta commands default to `meta` for status/set/delete):
- `kulturbytes-social/meta`: `system-user-access-token` (`META_SYSTEM_USER_ACCESS_TOKEN`), shared by Facebook and Instagram.
- Legacy `kulturbytes-social/facebook`: `page-access-token` (`FACEBOOK_PAGE_ACCESS_TOKEN`), `user-access-token` (`FACEBOOK_USER_ACCESS_TOKEN`).
- Legacy `kulturbytes-social/instagram`: `access-token` (`INSTAGRAM_ACCESS_TOKEN`).
- `kulturbytes-social/mastodon`: `access-token` (`MASTODON_ACCESS_TOKEN`).

Platform subcommands retain `--credentials status|set|delete`
and default `--credential meta` for Facebook/Instagram. Legacy selectors are
`page|user` for Facebook and `access` for Instagram; Mastodon keeps `access`. Status shows only
presence according to resolution precedence. Set prompts with `hide_input=True`;
delete requires confirmation and affects only keyring storage. Reject combinations
with `--publish`, `--check-auth`, or Facebook `--resolve-page-token`; ignore event-selection flags during management.
No event/network/database operation may run during credential management.

Only OS backends (Secret Service, KWallet, macOS Keychain, Windows Credential Locker,
or chains consisting solely of those) are accepted; reject file/plaintext/null/fail
backends. Backend exceptions are converted to concise Click errors without raw details.
Never display token values, fragments, lengths, or hashes. Persist validated primary
Meta tokens only through the central atomic `.env` writer. Never put tokens in SQLite,
logs or shell startup files; temporary writer files must be restrictive and cleaned up. Non-secret IDs, API versions,
Meta login types and IDs also follow .env > environment; Mastodon instance config also follows .env > environment > default. Meta shares one service across Facebook/Instagram; Mastodon is separate. Changing
accounts requires matching asset access.

Ubuntu optional packages: `sudo apt install gnome-keyring libsecret-tools`. Use an
unlocked Secret Service session. Keyring is optional for headless/CI/systemd/container
execution with env tokens; deployment-managed systemd credentials may be preferable,
with explicit external handoff to the environment (no provisioning automation here).
All tests must mock keyring API/backend access completely and preserve guarantees
from repeat publishing, date validation, auth preflight and Mastodon instance limits.

## SQLite deduplication

The publishers use separate SQLite databases with incompatible platform-specific schemas. Initialization verifies existing platform ID columns and claims `publisher_metadata` under a transaction, rejecting another platform before schema writes. Use `FACEBOOK_DATABASE_PATH`, `INSTAGRAM_DATABASE_PATH`, or `MASTODON_DATABASE_PATH`; each uses shared `.env > environment` resolution. These keys take precedence over deprecated `DATABASE_PATH` (once-per-process warning), then defaults; relative values resolve against the platform default database directory, not CWD. In a source checkout, defaults remain anchored at `REPO/PLATFORM/PLATFORM_posts.sqlite3` to reuse existing state. Outside a checkout, defaults are `$XDG_DATA_HOME/kulturbytes-social/PLATFORM_posts.sqlite3` or `~/.local/share/kulturbytes-social/PLATFORM_posts.sqlite3`. Absolute overrides are used directly. Existing non-default databases must be selected explicitly when migrating; never silently copy or merge them. Parent directories are created only during database initialization. Dry run may create the database and tables but does not reserve an attempt or record a publication.

Default names:

```text
facebook_posts.sqlite3
mastodon_posts.sqlite3
instagram_posts.sqlite3
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

All publishers use `INSERT ... ON CONFLICT(date_uuid) DO UPDATE`. A confirmed repeat publication with `--include-published` replaces the stored remote publication ID (and Mastodon status URL), updates event metadata, and refreshes `published_at` after remote success. The legacy table retains the latest publication per date; the new journal retains each attempt. Failed remote publication leaves the existing legacy record unchanged.

---

## Boundary validation, media security and read retries

- `models.py` validates discovery and detail responses with strict Pydantic models;
  publishers receive `model_dump(exclude_unset=True)` dictionaries for compatibility.
  Model only consumed fields. Optional fields may be absent or null. Identifiers are
  bounded non-empty safe path segments, not UUID objects, to retain opaque/simplified IDs.
- Invalid discovery envelopes fail; malformed individual records are reported/skipped.
  An invalid matching direct target fails nonzero even if a valid sibling matches too.
  Event UUID, date UUID and slug must match the validated detail response before publishing.
  Keep the list-summary/detail-description precedence.
- `timezone.application_today()` is the only business-day clock and uses Europe/Berlin.
- All media downloads and Instagram's JPEG check use `media_security.media_response`.
  The allowlist contains only `api.kulturbytes.de`, HTTPS port 443, based on existing
  repository media examples. No arbitrary hosts/IP URLs or speculative CDN entries.
  Reject credentials and any DNS answer that is non-global/reserved. Resolve once
  per attempt and give `PublicMediaTransport` the validated numeric TCP destination;
  HTTPcore's `sni_hostname` extension and original Host header preserve certificate
  hostname validation. TLS verification remains on. Never fall back to hostname DNS.
- A separate media client/HTTPTransport uses `trust_env=False`, no proxy, no API auth
  or cookies. Every retry/redirect repeats the policy (max five redirects). The single
  allowed origin prevents IP-keyed TLS pool reuse across different server names;
  revisit pool isolation before extending the host allowlist. No custom socket code.
  Tests exercise the real HTTPX/HTTPcore stack with a fake TCP/TLS backend and a
  rebinding resolver; no real DNS/network. Meta's later Instagram fetch is outside
  the local transport. Do not claim control over it. Issue #6 size limits stay open.
- `http.safe_get` reuses the caller's client, disables automatic redirects, and tries
  at most three times on 429/502/503/504 or ConnectTimeout/ReadTimeout/ConnectError.
  Backoff is 0.5/1 seconds; Retry-After integer/HTTP-date is clamped to 0–5 seconds.
  Inherit the client timeout unless an explicit request override is supplied,
  including explicit None. No hidden global five-second timeout; attempt count and
  delays remain bounded independently from configured network-phase timeouts.
  Streaming retries cover request/header acquisition; failures while consuming a body
  fail closed without resume. Keep existing application polling intervals separate.
- No publishing POST retries, including image uploads and Instagram containers.
  Workflow errors must not print raw third-party exceptions or credential-bearing URLs.
  Authenticated API payloads go through shared redaction; journal errors store only classes.

## Publication attempts and concurrency

`publications.py` owns one shared state mechanism for all publishers. Initialize
`publication_attempts` alongside the platform's existing `published_events`, without
removing legacy rows. Journal fields include attempt UUID, platform, date/event UUID,
state, remote ID/URL, error class, timestamps, date_slug and a metadata snapshot.
`target_ref` is a bounded numeric Facebook Page/Instagram User ID or a normalized
credential-free Mastodon origin. `content_sha256` hashes canonical UTF-8 JSON
(sorted keys, compact separators) containing lowercase platform, event/date UUIDs,
date_slug and the exact final message. Pass already-built text/caption; never rebuild
it differently for hashing. Never persist credentials or the social body. Add the
new nullable columns non-destructively; old rows retain NULL for unknown context.

After per-event confirmation, `execute_publication` atomically reserves the date.
`reserve_attempt` uses `BEGIN IMMEDIATE`, rechecks completed deduplication unless an
explicit repeat was confirmed, and a partial unique index on `(platform, date_uuid)`
for states `reserved`, `publishing`, `remote_succeeded`. `begin_remote_mutation` commits
`publishing` plus the concrete `mutation_stage` before each content-creation POST:
`facebook_photo`, `facebook_feed`, `mastodon_media`, `mastodon_status`,
`instagram_container`, `instagram_publish`. Keep the latest stage on uncertainty.
Transactions do not span remote
requests. `busy_timeout=5000` and foreign keys are enabled; existing journal mode is
retained instead of forcing WAL.

State flow: `reserved → publishing → remote_succeeded → published`. Record returned
post IDs immediately before finalizing the legacy publication row. A failure before
remote mutation or a definitive POST rejection may become `failed`; 408, transport
errors and 5xx remain active, with the error class but no raw response persisted.
A failing polling GET cannot classify the preceding POST as a definitive rejection.
Never downgrade confirmed remote success.
If finalization fails, retain `remote_succeeded`; if saving even the returned ID fails,
the prior durable reservation remains active and the error reports the ID. A crash
between remote success and its local persistence is still ambiguous; no distributed
transaction or exactly-once guarantee is claimed.

Unresolved attempts block selection and reservation, including `--include-published`.
There is no automatic expiration. Dry runs and declined confirmations create no attempt.
Completed explicit repeats create a new attempt UUID and update the latest legacy row.
Different platform databases and different dates can proceed independently.

Transactions have explicit owners: `_transition` only updates SQL; public standalone
state services own their transactions. Publication finalization and `resolve_attempt`
each own one transaction for legacy-row and final-state updates. Their callbacks
must call platform `remember_post(..., commit=False)`; standalone legacy writes keep
commit=True compatibility. Resolve must not call a service that commits internally.
A failed recovery rolls back all changes in that operation, preserving any remote
success committed before it. Never overwrite a confirmed ID/URL during recovery.

The root CLI provides `attempts list --platform PLATFORM` with SQL filters `--state`,
`--active`, `--date-uuid`, `--limit` (default 50, zero means all, newest first;
inactive states conflict with --active), and
`attempts resolve --platform PLATFORM ATTEMPT_UUID --outcome published|failed`.
Recovery is local, requires no token and never calls a platform API. The operator must
stop the worker and inspect the platform first, then explicitly confirm the result.
Use the stored remote ID for `remote_succeeded`; otherwise `published` requires
`--remote-id` with numeric platform ID syntax (optional Mastodon `--remote-url`
without credentials/query/fragment). `failed` may release only a reserved
or publishing attempt with confirmed absence of a remote post. Never automatically
clear reservations or delete remote posts. See README for operational examples.

## Social hashtags

Use the detailed event field:

```python
event.get("tags") or []
```

Normalize every non-empty tag into a hashtag, discarding values that contain no usable characters. Mastodon preserves all generated hashtags, including `#Kulturbytes` and the city. If required metadata and hashtags do not fit the resolved limit, fail closed rather than truncating them.

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

Current implementation: `strip_markdown` lives in `kulturbytes_common.formatting` and is used by Mastodon and Instagram. It handles a subset of Markdown. Facebook `build_message` currently passes Markdown through; integrating it there remains a future fix.

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
META_SYSTEM_USER_ACCESS_TOKEN
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

The Mastodon CLI resolves `configuration.statuses.max_characters` from public
`GET /api/v2/instance` once, when the first valid selected event reaches formatting,
and reuses it for the invocation. Metadata reads require no social credentials;
`--check-auth` does not fetch instance metadata. Each nesting level is checked
and only a positive integer (not bool/string/float) is accepted. HTTP/transport
errors, invalid JSON, and missing/malformed values produce a concise warning
and a 500-character fallback. No extra authenticated retry is made.

Composition and preview use Python `len()` as the application character count.
Instance-specific URL reservation and grapheme counting are not implemented;
server-side validation can therefore differ. See the official [instance API](https://docs.joinmastodon.org/methods/instance/)
and [configuration fields](https://docs.joinmastodon.org/entities/Instance/).

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

The builder keeps title, date/time, venue/city, the complete Kulturbytes URL,
and all hashtags as required content. Optional metadata is included as whole fields
in priority order: subtitle, price, ticket URL, organizer. Summary/description
receives the remaining space and is trimmed only at word boundaries; an oversized
single word is omitted. Required-content overflow raises a clear error before
confirmation or media upload and leaves publication records unchanged.
The final message is built once per event, displayed with the resolved limit,
and passed unchanged to the status request. Never slice the complete message.

---

# Instagram publisher

Implementation: `instagram/src/kulturbytes_instagram/cli.py`, using the shared workflow.
Keep interactive/direct selection, list-summary/detail-description priority, filtering,
confirmation and dry-run behavior aligned with the other platforms.

- Only single-image feed posts are supported. Use the detail `images.main.url`.
- Instagram fetches the public JPEG URL itself. The publisher checks the JPEG signature
  with a read-only image request, also in dry run. Missing/non-JPEG images fail the event;
  there is no text fallback, image conversion, external hosting, or generated image.
  Image dimensions and other platform restrictions are validated remotely by Meta.
- Legacy `INSTAGRAM_LOGIN_TYPE=instagram` (default only without a shared Meta token) uses `graph.instagram.com` with an Instagram
  User Access Token and `instagram_business_basic` / `instagram_business_content_publish`.
  `facebook` uses `graph.facebook.com` and requires a linked professional Instagram account
  and the appropriate Facebook Login permissions, including `instagram_basic` and
  `instagram_content_publish`. See `instagram/README.md` for setup.
- `INSTAGRAM_USER_ID` is the numeric Instagram account ID for the selected login flow;
  the resolved shared Meta token (or deprecated `INSTAGRAM_ACCESS_TOKEN`) must match it. Neither is required for preview/help; both are required for `--publish` and `--check-auth`.
  `INSTAGRAM_GRAPH_API_VERSION` defaults to `v26.0`, matching the project's Meta version default.
- The caption has an application limit of 2,200 characters and up to five generated
  hashtags, prioritizing Kulturbytes and city. Trim summary first, preserve the full
  Kulturbytes URL and whole hashtags, and reject overlong fixed metadata.
- After confirmation, create `POST /{user_id}/media` with `image_url` and `caption`;
  poll `GET /{container_id}?fields=status_code,status` up to five times, 60 seconds apart.
  Only `FINISHED` permits `POST /{user_id}/media_publish` with `creation_id`.
  Error, expiration, unexpected status or timeout must not record success.
- Store the confirmed media ID in `instagram_posts.sqlite3`, keyed by `date_uuid`.
  Like the other publishers, an explicitly confirmed repeat uses an upsert and
  replaces the saved media ID. Do not automatically retry publication after transport errors.
- Tests in `tests/test_instagram.py` simulate the HTTP sequence, errors, polling, caption
  limits, image checks, CLI confirmation, direct selection and SQLite deduplication.

API reference: [Meta's Instagram publishing documentation](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-ab559ffb-8e2c-4b0a-b43a-5737b6d2f672).

---

## Message composition

Platform-neutral content is represented by `SocialItem`. Final text composition lives in the Jinja templates, with the shared renderer enforcing platform limits. The platform builders are thin canonical wrappers around `render_post`.

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
strip_markdown
```

Existing platform-specific helpers include:

```text
build_message  # Facebook
build_mastodon_message
publish_facebook_photo
publish_text_post  # Facebook
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

and report the response payload on failure after redacting secrets. This is a target requirement: current Kulturbytes/image requests do not print response bodies, media polling does not call `raise_for_status()`, while authenticated Facebook and Mastodon publication responses and all authentication preflights use shared secret redaction. Instagram also uses shared redaction for API error payloads. All three send tokens as Authorization headers.

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
META_SYSTEM_USER_ACCESS_TOKEN=
FACEBOOK_GRAPH_API_VERSION=v26.0
FACEBOOK_DATABASE_PATH=facebook_posts.sqlite3
```

### Mastodon

```env
MASTODON_BASE_URL=https://norden.social
MASTODON_ACCESS_TOKEN=
MASTODON_DATABASE_PATH=mastodon_posts.sqlite3
```

Do not include real secrets in `.env.example`. All publishers read authentication settings from the deterministic `.env` before process environment.

---

## Dependency management

Use Python 3.12 or newer. The repository is a `uv` workspace with a root application package and four internal packages and one root `uv.lock`. Add or remove dependencies in the package that uses them with `uv`.

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
uv run kulturbytes-social facebook
```

from the repository root; replace `facebook` with `mastodon` or `instagram` as needed. Only the root package declares `[project.scripts]`. It depends on the platform workspace packages, which depend on common; common must never import the root CLI.

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

They cover selection parsing, basic address/hashtag/price formatting, mocked image downloads, both dry-run CLIs, publication confirmation, SQLite records and duplicate filtering, filtering/sorting/limits, and confirmed repeat publications (updated IDs, metadata, timestamps, and unchanged records on remote failure). Publication functions are mocked in the confirmed-publish test; this does not verify the actual platform HTTP requests.

Tests in `test_api_models.py`, `test_media_security.py`, `test_http_retry.py`, `test_timezone.py`, `test_database_paths.py`, `test_publication_journal.py`, `test_attempts_cli.py` and `test_concurrency.py` cover boundary validation, SSRF/redirects, retries, Berlin dates, schema ownership, actual mocked POSTs, SQLite finalization failure/recovery and separate-connection reservations. Mock DNS and sleep; use fresh databases for uncertain-failure subcases so reservations do not hide later cases. Do not use live social publishing in automated tests. Full Markdown support, download sizes and reliable Mastodon media processing remain gaps.

---

## Current project structure

The shared implementation already exists as a `uv` workspace:

```text
pyproject.toml                 # root application, public script, workspace members
src/kulturbytes_social/cli.py   # root Click group and command registration
src/kulturbytes_social/attempts.py # explicit local publication recovery
uv.lock                        # shared lockfile
common/src/kulturbytes_common/
    events.py                  # API reads, dates, URLs, hashtags, prices
    media.py                   # image URLs and downloads
    formatting.py              # Markdown normalization
    selection.py               # interactive selection
    database.py                # paths, schema ownership, duplicate lookup
    models.py                  # strict API boundary
    timezone.py                # Berlin business clock
    http.py                    # safe GET retries
    media_security.py          # public HTTPS / DNS / redirects
    publications.py            # journal, reservations, recovery
    sources/                   # SocialItem, YAML/JMESPath and source adapters
    rendering.py               # sandboxed Jinja and platform text constraints
    data/                      # packaged sources and templates
    storage.py                 # compatible platform schemas and journal snapshots
    workflow.py                # canonical filtering and publishing loop
facebook/
    src/kulturbytes_facebook/cli.py
mastodon/
    src/kulturbytes_mastodon/cli.py
instagram/
    src/kulturbytes_instagram/cli.py
tests/test_publishers.py
tests/test_instagram.py
```

Each platform owns configuration, previews, confirmation and publication calls. Shared `sources/`, `rendering.py` and `storage.py` own adaptation, text composition and compatible platform schemas/writers. The root CLI directly registers `facebook_command`, `mastodon_command`, and `instagram_command`. Credential management remains platform-scoped through the existing options, e.g. `kulturbytes-social facebook --credentials set --credential meta`; do not duplicate credential logic in the root. Tests invoke the root CLI for all platform scenarios. Preserve the dependency direction root → platform → common.

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
