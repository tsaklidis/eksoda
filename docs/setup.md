# Setup guide

This guide gets the Eksoda backend running on a development machine, shows how
to try the API end to end, and lists the commands used day to day. Production
deployment is covered separately in [deployment.md](deployment.md).

## Contents

1. [Prerequisites](#1-prerequisites)
2. [First run](#2-first-run)
3. [Trying the API](#3-trying-the-api)
4. [Development workflow](#4-development-workflow)
5. [Receipt tooling](#5-receipt-tooling)
6. [Configuration](#6-configuration)
7. [Services](#7-services)
8. [Troubleshooting](#8-troubleshooting)

## 1. Prerequisites

- Docker Engine or Docker Desktop with Compose v2
- GNU `make`
- `git`

Nothing else is installed on the host: Python, PostgreSQL and Redis run in
containers, and every `make` target wraps `docker compose`.

## 2. First run

```bash
git clone https://github.com/tsaklidis/eksoda.git
cd eksoda
make up
make bootstrap EMAIL=you@example.com HOUSEHOLD="Home"
```

**What these commands do:**

- **`make up`:**
  - creates `.env` from `.env.example` on first run
  - builds the images and applies migrations
  - starts the API, the Celery worker and the Celery beat scheduler
- **`make bootstrap`:** creates the first user, who owns a household, and prompts for a password.

| URL | Purpose |
|---|---|
| <http://localhost:8000/api/docs/> | Swagger UI. Log in with `POST /api/v1/auth/login`, then use **Authorize** with the access token |
| <http://localhost:8000/api/schema/> | OpenAPI schema, the contract for clients |
| <http://localhost:8000/admin/> | Django admin. Create a staff user with `make superuser`, or run `make bootstrap ARGS=--superuser` |
| <http://localhost:8000/healthz>, `/readyz` | Liveness and readiness checks |

The development stack publishes only on `127.0.0.1`:

- the API on `API_HOST_PORT` (default 8000)
- PostgreSQL on `DB_HOST_PORT` (default 55432)

To fill the analytics with sample data, find the household id (it is printed by `make bootstrap`) and run:

```bash
make manage ARGS="seed_demo_data --household <household id>"
```

## 3. Trying the API

All endpoints live under `/api/v1/`, take and return JSON, and use JWT bearer
tokens. Errors always have the same shape:

```json
{"error": {"code": "receipt_not_found", "message": "…", "details": {}}}
```

### Log in

```bash
curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email": "you@example.com", "password": "…"}'
```

The response holds an `access` token (15 minutes) and a `refresh` token
(30 days, rotated on every use). Send the access token as
`Authorization: Bearer <token>`.

### Import a receipt

1. **Submit the link from the receipt's QR code:** `POST /api/v1/receipts/import` with `{"url": "<link>"}`.
   - A new link gets `202` with an import id.
   - The same link again gets `200` with the existing import (`"duplicate": true`).
2. **Follow the import:** `GET /api/v1/receipt-imports/{id}`. The worker fetches and parses the page in the background.
   - Temporary failures are retried automatically, after about 1 min, 5 min, 30 min, 2 h, 6 h and 24 h.
   - A failed import shows a stable error code and can be retried with `POST /api/v1/receipt-imports/{id}/retry`.
3. **Read the receipt:** `GET /api/v1/receipts/{id}` returns the merchant, store, totals and every line.

### Products and prices

- **New items:** each new item on a receipt becomes a household product, with its package size when the description states one (`… 1L`, `… 195G`). The next purchase of the same item at the same shop is matched to it.
- **Reused item codes:** when a shop reuses an item code for something else, the line goes to `GET /api/v1/receipt-items/review` instead of being matched.
- **Merging:** the same product bought at different shops can be merged with `POST /api/v1/products/{id}/merge`.
- **Price history and comparison:**
  - `GET /api/v1/products/{id}/prices` returns the price history per kg, liter or piece.
  - `GET /api/v1/products/{id}/price-comparison` ranks shops when their prices are comparable.

### Spending analytics

`GET /api/v1/analytics/` + `summary`, `spending-by-category`,
`spending-by-merchant`, `monthly-trend` or `top-products`. Each takes `from`
and `to` (household-local dates; the current month by default). Spending by
category always adds up to total spending.

### Households and invitations

- **Registration is invite-only** by default (`REGISTRATION_OPEN=false`).
  - An owner creates a code with `POST /api/v1/households/{id}/invitations`.
  - A new person registers with `invite_code`.
  - An existing user joins with `POST /api/v1/households/join`.
- **Household selection:** household-scoped endpoints accept an optional `X-Household-ID` header, which is required only for users in more than one household.

## 4. Development workflow

```bash
make help                                   # every target with a description
make test ARGS="tests/accounts -k login"    # run selected tests
make check                                  # lint, format, migration check, tests with coverage
make fmt                                    # format and auto-fix
make makemigrations && make migrate         # after changing models
make lock                                   # after changing dependencies in backend/pyproject.toml
make shell                                  # Django shell
make logs ARGS=worker                       # follow logs of one service
make down                                   # stop the stack
make clean                                  # stop and delete the development database
```

**`make check` must pass before a change is complete.** It runs:

- `ruff` lint and format checks
- `makemigrations --check`
- the test suite, which must keep at least 85% coverage (the current suite is at about 98%)

**Conventions:**

- Business logic lives in `services.py` modules. Views stay thin.
- Money and quantities are always `Decimal`.
- Every household-scoped endpoint uses `HouseholdScopedMixin`, and every API route is listed in `tests/test_isolation.py`, so a new endpoint cannot skip the isolation test.
- Receipt provider code under `backend/apps/receipts/providers/` is pure Python with no Django imports, and is checked by a test.
- Tests never touch the network, except those marked `live`.

The [technical design](technical-design.md) describes the modules and these rules in detail.

## 5. Receipt tooling

**Supported sources:**

- Impact (`einvoice.impact.gr`)
- Entersoft (`e-invoicing.gr`, used by LIDL among others)
- the AADE cash-register check page (`www1.aade.gr/tameiakes`, which gives totals only)

These commands do not use the database:

```bash
make parse-receipt SRC="<receipt url>"                                   # fetch, parse and validate
make parse-receipt SRC=tests/fixtures/entersoft/lidl_21_lines.html ARGS=--json
make sanitize-fixture PROVIDER=impact IN=/abs/path/raw.html OUT=tests/fixtures/impact/name.html
make test-live URLS="<url> <url>"                                        # opt-in tests against real sources
make test ARGS="tests/receipts/test_fixtures.py --update-golden"         # rewrite golden files, then review the diff
```

**Receipt links work like passwords:** anyone who has one can open the receipt.

- The tools print links masked.
- Keep raw saved pages outside the repository.
- Commit only fixtures produced by `sanitize-fixture`.

Supporting a new provider or a changed page layout is a provider-only change. The [deployment runbook](deployment.md#8-runbook-a-provider-changed-its-page-format) describes the steps.

## 6. Configuration

All settings come from `.env`. [`.env.example`](../.env.example) documents
every variable with its default. The ones most often changed in development:

| Variable | Default | Purpose |
|---|---|---|
| `API_HOST_PORT` / `DB_HOST_PORT` | `8000` / `55432` | Host ports of the development stack |
| `REGISTRATION_OPEN` | `false` | Allow registration without an invitation code |
| `THROTTLE_*` | see `.env.example` | Rate limits for login, registration and imports |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `console` | Logging |

Production settings (`DOMAIN`, ports, process counts, backups, Sentry) are
described in [deployment.md](deployment.md#3-first-deployment).

## 7. Services

| Service | Role |
|---|---|
| `db` | PostgreSQL 17, the source of truth |
| `redis` | Celery broker, cache and rate-limit counters. Disposable: no data lives only here |
| `migrate` | Applies migrations once, before the application services start |
| `api` | Django and Django REST Framework (`runserver` in development, gunicorn in production) |
| `worker` | Celery worker for the `imports` and `maintenance` queues. Reloads on code changes in development |
| `beat` | Celery beat: schedules due imports every minute and daily maintenance |
| `proxy` | Production only: Caddy, HTTPS |
| `backup` | Production only: daily `pg_dump` with 30-day rotation |

## 8. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `make up` fails with a port already in use | Another service uses 8000 or 55432. Change `API_HOST_PORT` or `DB_HOST_PORT` in `.env` |
| `readyz` returns 503 | PostgreSQL or Redis is not reachable. Check `make ps` and `make logs ARGS=db` |
| An import stays `pending` | The worker is not running or cannot reach the provider. Check `make logs ARGS=worker`. Retries are scheduled in the database, so restarting the worker loses nothing |
| An import fails with `provider_format_changed` | The provider changed its page. Follow the [runbook](deployment.md#8-runbook-a-provider-changed-its-page-format) |
| Tests fail after a model change | Run `make makemigrations`, review the migration, then `make check` |
