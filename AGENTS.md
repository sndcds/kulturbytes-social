# AGENTS.md

## Architecture and scope

Kulturbytes Social publishes event dates to Facebook Pages, Instagram single-image feeds
and Mastodon. Kulturbytes remains the source of truth. The sole CLI is
`kulturbytes-social`; the platform packages contain server-side publisher adapters.

PostgreSQL is the only persistent database. Do not add alternative stores, legacy data
importers, compatibility adapters, old file-path settings or fallback publication paths.
Existing local historical data is outside this repository's scope and must not be read,
changed or imported. Operators handle any historical-data transfer externally.

The request path is:

```text
Click CLI / HTTP client -> FastAPI routes -> services -> repositories / publisher adapters
```

- CLI code uses HTTP for events, previews, publication, auth checks and attempt recovery.
  It must not import repositories, SQLAlchemy or platform publishing modules.
- Routes validate transport data and delegate to services. Domain services do not depend
  on FastAPI or Click UI. Existing format/auth helpers may still raise Click errors;
  services translate those into secret-safe domain failures.
- Repositories own short transactions, with no social HTTP calls inside them.
- Adapters retain platform formatting, configuration and HTTP details, and never import FastAPI.
- App import and CLI help must not connect to a database or require platform credentials.
- No distributed queue or background scheduler exists. Jobs execute synchronously.

## Workspace and dependencies

Use Python >= 3.12, `uv`, `httpx` and `click`. Do not introduce `requests`.
The root application plus `common`, `facebook`, `instagram`, `mastodon` share one `uv.lock`.
Use `uv add`, `uv remove`, `uv sync`; add dependencies to the consuming package.
There are no platform `main.py` wrappers or separate console commands.

```bash
uv sync --all-packages
uv run kulturbytes-social --help
uv run alembic upgrade head
uv run uvicorn kulturbytes_social.api.app:app --host 127.0.0.1 --port 8000
```

Key directories:

```text
src/kulturbytes_social/api/             app, dependencies, schemas, versioned routes
src/kulturbytes_social/services/        events, publications, platforms, jobs
src/kulturbytes_social/db/              SQLAlchemy models, sessions, repositories
src/kulturbytes_social/client.py        HTTP-only CLI transport
src/kulturbytes_social/cli.py           selection and confirmation
src/kulturbytes_social/attempts.py      HTTP journal/recovery commands
common/src/kulturbytes_common/          event validation, media, credentials, helpers
facebook/src/kulturbytes_facebook/publisher.py
instagram/src/kulturbytes_instagram/publisher.py
mastodon/src/kulturbytes_mastodon/publisher.py
alembic/versions/                       explicit schema migrations
tests/                                 unit, CLI, API and real PostgreSQL tests
```

## Event discovery and text

Discover via `GET https://api.kulturbytes.de/api/events`, envelope `data.events`.
Resolve selected event UUID and date slug via
`GET https://api.kulturbytes.de/api/event/{uuid}/date/{date_slug}`, envelope `data`.
Always enrich from details. Require detail event UUID, date UUID and slug to match discovery.
Reuse the Pydantic boundary validation; skip malformed siblings while rejecting malformed
explicit targets. Keep opaque IDs and Unicode support.

Use the selected list record's nonempty `summary`, otherwise detail `description`.
Whitespace-only summaries are empty. Never use detail `summary` as fallback. Compose on a
copy without mutating API responses. Optional metadata may be absent.

The public link is `https://kulturbytes.de/de/veranstaltung/{uuid}/{date_slug}`.
The deduplication identity is `platform + date_uuid`, including recurring dates.
Offer released events today/future in `Europe/Berlin`. Preserve case-insensitive exact
city filtering, sorting, limit 50 (0 = all), and exclusion of published/active dates.
Direct selection accepts UUID plus either slug or date UUID before list limit, requires
exactly one match and retains filters. Detail release status is not separately rechecked.

CLI selection accepts numbers, comma lists, ranges, `all`, `alle`, `*`; empty exits.
Preview is default. Publishing requires local per-event confirmation. Known dates require
`--include-published` and another confirmation even in dry run. Active/uncertain attempts
always block. API clients explicitly authorize publishing via authenticated POST and
repeats via `force_repeat`; no terminal prompts in the backend.

Use detail `images.main.url` for images and detail tags for hashtags. Normalize tags,
deduplicate case-insensitively, include `#Kulturbytes` and city. Shared helpers include
URL/date/address/price/hashtag formatting, Markdown stripping and secure media downloads.
Keep final platform composition separate. Existing limitations: Facebook still passes
Markdown through; Mastodon uses Python character counting and its existing media polling
warns and continues after exhaustion. Do not claim these gaps were fixed by this refactor.

## PostgreSQL state and transactions

`DATABASE_URL` must use `postgresql+psycopg`; never log its value. SQLAlchemy 2 declarative
models use UUID, JSONB for job data and timezone-aware UTC TIMESTAMPTZ. Alembic is the only
production schema creation path. Current initial revision is `0001_postgresql`.

Tables:

- `publication_attempts`: event/date identity, platform, state, phase, target, content hash,
  remote ID/URL, sanitized error class/message, timestamps.
- `publications`: confirmed historical rows referencing attempts. Explicit repeats create
  new rows; never add a unique constraint on platform/date here.
- `jobs`: queued/running/succeeded/failed/cancelled, validated non-secret payload/result.

The partial unique index on attempts permits at most one active platform/date pair in
`reserved`, `publishing`, `remote_succeeded`. Transaction-scoped advisory locks serialize
history checks and reservation/finalization. Never rely on a Python process lock for this.

Reserve before remote mutation. Commit the current phase immediately before every POST:
`facebook_photo`, `facebook_feed`, `mastodon_media`, `mastodon_status`,
`instagram_container`, `instagram_publish`. Hash the actual final text with platform and
event/date identity. Persist only bounded, validated target references and remote IDs.
No tokens, headers, environment snapshots, response bodies or full event payloads in the journal.

Confirmed remote success must be committed as `remote_succeeded` with its remote ID BEFORE
final bookkeeping. Publication insertion and `published` state form one atomic transaction.
A bookkeeping failure must preserve the prior blocker and saved remote reference. A failure
to save the remote reference must retain the already committed mutation state. POSTs are
never retried automatically. GET retries remain bounded and opt-in.

Manual resolution requires authentication, `confirmed: true` and operator verification
that the worker has stopped and the platform was inspected. It performs no social requests.
Do not replace a saved remote reference. Failed resolution is limited to reserved/publishing;
cancellation to reserved. Never automatically expire active/uncertain attempts.

## API and secrets

App: `kulturbytes_social.api.app:app`; factory: `create_app()`.
Public `/health` is liveness; `/api/v1/health` checks PostgreSQL schema/readiness and returns
503 on failure. All business routes require `KULTURBYTES_SOCIAL_API_TOKEN` as Bearer token,
compared using `secrets.compare_digest`. Missing server configuration fails closed.
No account/role system exists. OpenAPI is available at `/docs`.

The CLI uses `KULTURBYTES_SOCIAL_API_URL`, default loopback port 8000, and the shared API token.
Platform credentials are resolved only server-side. Preview must never authenticate to a
social platform or write attempts, publications or jobs. Read-only image/instance requests
are allowed in preview. Auth checks perform no social mutations or publication-state writes.

Configuration priority: nonempty `.env` > environment > OS-keyring for secrets. Explicit
empty environment credentials suppress the keyring. Use existing environment helpers for
stable checkout/XDG paths and atomic secret file updates. Preserve shared Meta System User
configuration and supported platform credentials. The backend never prompts for secrets.
Local `--credentials` management remains for operators; it affects the executing machine.

Use secret-safe domain exceptions/HTTP responses and generated request IDs. Never expose raw
SQLAlchemy/driver exceptions, API tokens, Social tokens, Authorization headers or upstream URLs
containing credentials. Bind loopback by default; document HTTPS for remote use.

Preserve media SSRF defenses: HTTPS allowlisting, public DNS validation and pinning, TLS/SNI,
proxy isolation, redirect revalidation. Instagram requires a public JPEG and a FINISHED
container before the final POST. No generated images or live publication in tests.

## Verification

```bash
uv sync --all-packages
uv run --all-packages python -m unittest discover -s tests -v
```

Real PostgreSQL integration tests require an explicit `TEST_DATABASE_URL` with driver
`postgresql+psycopg` and a dedicated name ending `_test`. Setup uses this exact connection,
not the backend `.env`, applies Alembic, then truncates the application tables between tests.
Without configuration those tests are skipped. Never use production data for tests.

Before completion, run the full suite with a dedicated PostgreSQL server, validate migration
upgrade from empty schema, concurrency across independent connections, partial success and
atomic rollback/recovery. Check API auth/redaction, CLI help/direct/interactive/confirmation,
mocked exact publisher HTTP stages, and manually inspect a simulated dry-run output.
Run `git diff --check`. Never publish to live social platforms to validate a change.
Update root/platform documentation when behavior or architecture changes.
