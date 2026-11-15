# Eksoda

The backend for a household expense and receipt app. It imports Greek
e-receipts from the URL in their QR codes, then keeps product price
history and household spending analytics. An Android scanner app and a
web frontend will consume this API later.

**Status:** Milestones 1 (foundation: authentication, households,
Docker stack), 2 and 2b (receipt parsing for Impact, Entersoft and AADE
cash-register receipts, SSRF-safe fetcher, validation), 3 (import
pipeline, stored receipts, import and receipt APIs), 4 (products,
matching, price history and comparison) and 5 (filters, merchants,
categories and spending analytics) and 6 (production stack, backups,
Sentry, security pass) are done. See `docs/implementation-plan.md` §6.

## Requirements

Docker (with Compose v2) and `make`. Nothing else is installed on the
host. Python, PostgreSQL and Redis all run in containers.

## Quick start

```bash
make up                                                # builds images, starts the dev stack
make bootstrap EMAIL=you@example.com HOUSEHOLD="Home"  # first owner (prompts for a password)
```

| URL | What |
|---|---|
| http://localhost:8000/api/docs/ | Swagger UI. Log in via `POST /api/v1/auth/login`, then **Authorize** with the access token |
| http://localhost:8000/api/schema/ | OpenAPI schema (the API contract) |
| http://localhost:8000/admin/ | Django admin (`make superuser`, or `make bootstrap ARGS=--superuser`) |
| http://localhost:8000/healthz, `/readyz` | Liveness and readiness checks |

`make up` creates `.env` from `.env.example` the first time. Edit it to
change ports, rate limits or open registration. The dev stack publishes
only to `127.0.0.1`: the API on `API_HOST_PORT` (default 8000) and
PostgreSQL on `DB_HOST_PORT` (default 55432).

## Daily commands

```bash
make help                               # all targets
make test ARGS="tests/accounts -k login"
make check                              # lint, format, migrations check, tests + coverage (must pass)
make makemigrations && make migrate
make lock                               # after changing dependencies in backend/pyproject.toml
make logs ARGS=worker
make down
make clean                              # also deletes the dev database volume
```

## Production

`compose.prod.yaml` adds HTTPS through Caddy, automatic restarts,
JSON logs and daily database backups. Only the proxy is published.

- **Access:** the home network and the VPN only, at a local name such as
  `https://eksoda.lan:8443`.
- **Certificate:** Caddy signs it with its own local CA. Export the root
  with `make prod-ca` and install it on each device.
- **Size:** fits a Raspberry Pi 4, about 400 MB of RAM in all.

```bash
make prod-up                                                 # build, migrate, start
make bootstrap PROD=1 EMAIL=you@example.com HOUSEHOLD="Home"  # first owner
make prod-logs ARGS="api worker"
```

Set `DOMAIN`, `DJANGO_SECRET_KEY`, the database password and the
allowed hosts in `.env` first. `docs/deployment.md` has:

- the full steps and the local DNS record
- installing the CA on phones and computers
- Raspberry Pi notes (ports taken by Pi-hole, memory limits, SD cards)
- updates
- the runbook for provider format changes

## Backup and restore

```bash
make backup [PROD=1]                                          # pg_dump into backups/
make restore FILE=backups/eksoda-….dump CONFIRM=yes [PROD=1]  # replaces the database
```

- Production also takes a dump every day and keeps 30 days of them.
- `make restore` first saves a safety dump of the current database.
- Copy `backups/` off the host regularly (`docs/deployment.md` §5).

## Receipt tools (no database involved)

Supported sources: Impact (`einvoice.impact.gr`), Entersoft (`e-invoicing.gr`, e.g. LIDL)
and the AADE cash-register check page (`www1.aade.gr/tameiakes`, summary only).

```bash
make parse-receipt SRC="<receipt url>"                               # fetch + parse + validate
make parse-receipt SRC=tests/fixtures/entersoft/lidl_21_lines.html ARGS=--json
make sanitize-fixture PROVIDER=impact IN=/abs/path/raw.html OUT=tests/fixtures/impact/name.html
make test-live URLS="<url> <url>"                                     # opt-in real-source tests
```

Receipt URLs work like passwords: anyone who has one can open the
receipt. The commands print them masked. Keep raw saved pages outside
the repository, and only commit fixtures produced by
`sanitize-fixture`.

## Services

| Service | Role |
|---|---|
| `db` | PostgreSQL 17, the source of truth |
| `redis` | Celery broker, cache and rate-limit counters. Disposable: no data lives only here |
| `migrate` | One-shot `migrate` before `api`, `worker` and `beat` start |
| `api` | Django + DRF (`runserver` in dev, gunicorn in prod) |
| `worker` | Celery worker (queues `imports`, `maintenance`). Auto-reloads in dev |
| `beat` | Celery beat: due imports every minute, daily maintenance |
| `proxy` (prod) | Caddy: HTTPS with a local CA, the only published service (LAN and VPN) |
| `backup` (prod) | Daily `pg_dump`, 30-day rotation |

## Importing receipts

1. `POST /api/v1/receipts/import` with `{"url": "<link from the QR code>"}`
   answers `202` with an import. Sending the same link again answers `200`
   with the existing import (`"duplicate": true`).
2. The worker fetches and parses the page in the background. Follow it with
   `GET /api/v1/receipt-imports/{id}`. Temporary failures are retried
   automatically (about 1 min, 5 min, 30 min, 2 h, 6 h and 24 h later).
3. A completed import points to its receipt: `GET /api/v1/receipts/{id}`.
   A failed import shows its error code and can be retried with
   `POST /api/v1/receipt-imports/{id}/retry`.

Import jobs, receipts, merchants and stores are also in the admin, which
can filter imports by status, provider and error code and retry them.

## Products and prices

- Each new item on a receipt becomes a household product automatically,
  with its package size when the description states it (`… 1L`,
  `… 195G`). The next purchase of that item at the same shop matches it.
- If a shop reuses an item code for something else, the line waits in
  `GET /api/v1/receipt-items/review` instead of being matched.
- The same product bought at different shops starts as separate
  products: merge them with `POST /api/v1/products/{id}/merge`.
- `GET /api/v1/products/{id}/prices` gives the price history per kg,
  liter or piece; `GET /api/v1/products/{id}/price-comparison` ranks
  shops when their prices are comparable.
- Receipts imported before matching existed are matched with
  `make manage ARGS="backfill_matching"`.

## Spending analytics

`GET /api/v1/analytics/summary`, `spending-by-category`,
`spending-by-merchant`, `monthly-trend` and `top-products` take `from`
and `to` (household-local dates; the current month by default). They
count active receipts in the household's currency that are not excluded
by the user; credit notes count negative. Spending by category always
adds up to total spending: lines without a product category use the
merchant's default category (set by staff in the admin), and discounts,
fees and unallocated amounts get their own buckets.

For a populated dashboard in development, after `make bootstrap`:

```bash
make manage ARGS="seed_demo_data --household <household id>"
```

## Accounts and households

- Registration is **invite-only** by default (`REGISTRATION_OPEN=false`).
  Steps:
  1. The first owner is created with `make bootstrap`.
  2. An owner creates an invitation code with
     `POST /api/v1/households/{id}/invitations`.
  3. A new person registers with `invite_code`, or an existing user
     joins with `POST /api/v1/households/join`.
- Household-scoped endpoints (receipts and imports) take an optional
  `X-Household-ID` header. It is required only for users in more than
  one household.
- Errors always have the shape
  `{"error": {"code": "...", "message": "...", "details": {...}}}`.

## Documentation

| Doc | Contents |
|---|---|
| `docs/requirements.md` | What is built: scope, decisions, data model, API, rules |
| `docs/technical-design.md` | How it is built: containers, modules, algorithms, tests |
| `docs/implementation-plan.md` | Milestones, exit criteria, status |
| `docs/deployment.md` | Production setup, Raspberry Pi notes, backups and restore, monitoring, runbook |
| `docs/providers/` | The real page formats of Impact, Entersoft and the AADE check page |
| `CLAUDE.md`, `.claude/` | Instructions and skills for Claude Code in this repo |
