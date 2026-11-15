# Technical Design: Server MVP

**Status:** M1, M2 and M2b are implemented. M3–M6 sections were trimmed
on 2026-11-14 (requirements D21) and are not implemented yet.
**Implements:** `docs/requirements.md` (v2). Section references (§) point
to that document unless they say otherwise.
**Plan:** `docs/implementation-plan.md`

This document describes *how* the server will be built: containers,
modules, models, services, algorithms, configuration and tests. Code
blocks are design sketches, not final code.

---

## 1. Architecture overview

```text
 Android app / future web client
            │  HTTPS, JSON, JWT
            ▼
 ┌────────────────────┐        ┌──────────────────────────────┐
 │ proxy (Caddy)      │  prod  │                              │
 └─────────┬──────────┘  only  │   PostgreSQL 17  (db)        │
           ▼                   │   - source of truth          │
 ┌────────────────────┐  SQL   │   - import job state         │
 │ api                │◄──────►│                              │
 │ Django + DRF       │        └──────────────▲───────────────┘
 │ gunicorn           │                       │ SQL
 └─────────┬──────────┘                       │
           │ enqueue (on commit)              │
           ▼                                  │
 ┌────────────────────┐   consume   ┌─────────┴──────────┐   HTTPS (pinned IP)
 │ redis (broker,     │────────────►│ worker (Celery)    │──────────────────► einvoice.impact.gr
 │ cache, throttles)  │             │ queues: imports,   │
 └─────────▲──────────┘             │ maintenance        │
           │ schedule               └────────────────────┘
 ┌─────────┴──────────┐
 │ beat (Celery beat) │  run due imports, flush expired tokens
 └────────────────────┘
```

**Principles**

- A modular monolith: one Django project, one image, and several
  processes (`api`, `worker`, `beat`).
- PostgreSQL holds all state. Redis is disposable: losing it loses
  queued messages and throttle counters, never data. The beat task
  re-enqueues due work from database state.
- Provider code is pure Python (no Django imports). Only the pipeline
  touches the ORM.
- **Everything runs in Docker,** including development, tests, linting,
  dependency locking and backups. The host only needs Docker.

### 1.1 Import flow

```text
client ──POST /receipts/import──► api
  api: validate URL → registry.resolve() → UrlIdentity
       get-or-create ReceiptImportJob (unique per household + identity)
       on_commit → process_import.delay(job_id)
  ◄── 202 {id, status: pending, duplicate: false}

worker: process_import(job_id)
  1 claim (short tx, SELECT … FOR UPDATE SKIP LOCKED): pending & due?
    → attempt_count += 1, next_attempt_at = now + lease
  2 provider.fetch()  ──SafeFetcher──► provider
  3 provider.parse() → CanonicalReceipt
  4 validate() → warnings
  5 one transaction: merchant/store → Receipt + items → classify → match
                     → normalized prices → job completed
  ✗ on error: rollback → job stays pending with next_attempt_at, or failed

beat: run_due_imports (every minute) → pending & due → enqueue
client ──GET /receipt-imports/{id}──► status / receipt_id
```

## 2. Repository layout

```text
eksoda/
├── compose.yaml                 # shared service definitions
├── compose.override.yaml        # development (auto-merged by `docker compose`)
├── compose.prod.yaml            # production overrides (proxy, backup)
├── .env.example
├── .gitignore                   # .env, .idea/, backups/, __pycache__, .coverage …
├── Makefile                     # the only entry point for daily commands
├── README.md
├── docs/
├── ops/
│   ├── Caddyfile
│   └── backup.sh
└── backend/
    ├── Dockerfile
    ├── .dockerignore
    ├── pyproject.toml           # deps, ruff, pytest, mypy, coverage config
    ├── uv.lock
    ├── manage.py
    ├── config/
    │   ├── settings/{base,dev,test,prod}.py
    │   ├── urls.py   api_urls.py   celery.py   wsgi.py
    ├── apps/
    │   ├── common/
    │   ├── accounts/
    │   ├── households/
    │   ├── merchants/
    │   ├── receipts/
    │   ├── products/
    │   └── analytics/
    └── tests/
```

### 2.1 Module responsibilities

| App | Owns | Key modules |
|---|---|---|
| `common` | Base models, money helpers, errors, pagination, household context, text and number utilities, health views, logging | `models.py`, `fields.py`, `errors.py`, `households.py`, `text.py`, `numbers.py`, `logging.py`, `health.py`, `schema.py` |
| `accounts` | `User`, authentication API, `bootstrap_household` | `models.py`, `api/`, `throttles.py`, `management/commands/` |
| `households` | `Household`, `HouseholdMember`, `HouseholdInvitation`, membership API | `models.py`, `services.py`, `api/` |
| `merchants` | `Merchant`, `Store`, resolution services (M3), read-only API (M5) | `models.py`, `services.py`, `api/` |
| `receipts` | Import jobs, receipts, items, providers, fetcher, validation, pipeline, classification | `canonical.py`, `mydata.py`, `providers/`, `fetching.py`, `validation.py`, `classification.py`, `services/`, `tasks.py`, `api/` |
| `products` | Categories, products, mappings, matching, units, normalized prices, review and merge | `models.py`, `matching.py`, `units.py`, `packages.py`, `prices.py`, `review.py`, `api/` |
| `analytics` | Read-only aggregate queries and API | `periods.py`, `queries.py`, `api/` |

### 2.2 Dependency rules

These are checked in code review and by a small import-linter style test.

- `receipts.providers.*`, `receipts.canonical`, `receipts.mydata`,
  `receipts.fetching` and `common.text` / `common.numbers` must **not**
  import Django models. They are plain Python.
- `receipts.services.pipeline` may call `merchants.services`,
  `products.matching` and `products.prices`. `products` must
  never import from `receipts.services`.
- `analytics` only reads. It never writes models.
- Cross-app foreign keys use string references (`"products.Product"`).

## 3. Containers and environments

### 3.1 Image (`backend/Dockerfile`)

One multi-stage Dockerfile with `dev` and `prod` targets:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.13-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:<pinned> /uv /uvx /bin/
WORKDIR /app

FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project --no-dev

FROM deps AS dev                       # used with a bind mount of ./backend
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM deps AS prod
COPY . .
RUN DJANGO_SETTINGS_MODULE=config.settings.prod DJANGO_SECRET_KEY=build-only \
    python manage.py collectstatic --noinput
RUN useradd --system --uid 10001 app && chown -R app /app
USER app
CMD ["gunicorn", "config.wsgi", "-b", "0.0.0.0:8000", "-w", "3", "--timeout", "30"]
```

- The virtualenv lives in `/opt/venv`, so the dev bind mount of `/app`
  does not hide it.
- Static files (admin, Swagger UI) are served by WhiteNoise. Swagger
  assets come from `drf-spectacular-sidecar`, so no CDN is needed.
- `uv.lock` is generated inside a container (`make lock`). No local
  Python is required.

### 3.2 Compose services

| Service | Image / target | Command | Notes |
|---|---|---|---|
| `db` | `postgres:17-alpine` | default | `pgdata` volume. Healthcheck `pg_isready` |
| `redis` | `redis:7-alpine` | `redis-server --save "" --appendonly no` | No persistence by design. Healthcheck `redis-cli ping` |
| `migrate` | backend | `python manage.py migrate --noinput` | One-shot. `api`, `worker` and `beat` wait for `service_completed_successfully` |
| `api` | backend | dev: `runserver`. prod: `gunicorn` | Healthcheck calls `/healthz` with Python's urllib (no curl in the slim image) |
| `worker` | backend | `celery -A config worker -Q imports,maintenance -c 2 -l info` | dev: wrapped in `watchfiles` for auto-reload |
| `beat` | backend | `celery -A config beat -l info -s /tmp/celerybeat-schedule` | Exactly one instance |
| `proxy` (prod) | `caddy:2-alpine` | `ops/Caddyfile` | LAN and VPN only. HTTPS for `$DOMAIN` with a certificate from Caddy's local CA (`tls internal`, root exported by `make prod-ca`). Listens on `HTTP_PORT`/`HTTPS_PORT` (default 80/443), the same numbers inside and out, with an explicit redirect that keeps the port. 1 MB body cap, no access log, no active health check (it would send `Host: api:8000`) |
| `backup` (prod) | `postgres:17-alpine` | `ops/backup.sh loop` | One `pg_dump -Fc` a day after `BACKUP_HOUR_UTC` into `BACKUP_DIR` (default `./backups`), written under a temporary name and owned by `BACKUP_OWNER` (the host user); deletes dumps older than `BACKUP_RETENTION_DAYS` (30). Starts after `migrate` |

- `compose.yaml` holds everything shared.
- `compose.override.yaml` (dev, applied automatically) switches to the
  `dev` target, bind-mounts `./backend:/app`, publishes
  `127.0.0.1:${API_HOST_PORT:-8000}` and
  `127.0.0.1:${DB_HOST_PORT:-55432}`, and sets
  `DJANGO_SETTINGS_MODULE=config.settings.dev`.
- One-off `make` commands start only `db` and `redis`
  (`docker compose up -d --wait db redis`), then run
  `docker compose run --rm --no-deps api …`. Tests use their own
  database, and `makemigrations` works before any migration exists.
- Celery workers log through Django's `LOGGING`: a `setup_logging`
  signal handler applies it, with `worker_hijack_root_logger=False`.
- Production: `docker compose -f compose.yaml -f compose.prod.yaml up -d`
  (`make prod-up`). `api` is not published. Only `proxy` is.
  - All services use `restart: unless-stopped` and rotated JSON-file logs.
  - The image builds with `network: host`. A Pi-hole on the same host in
    "local requests only" mode drops DNS queries from the build container's
    bridge subnet.
  - The app services set `DJANGO_SETTINGS_MODULE=config.settings.prod` and
    `LOG_FORMAT=json` themselves.
  - Sized for a small host (Raspberry Pi 4): `WEB_CONCURRENCY` gunicorn
    workers (default 2, recycled after 1000 requests) and
    `CELERY_CONCURRENCY` worker processes (default 1, recycled after 200
    tasks).
  - Every service has a `mem_limit`. Redis is capped at 64 MB with
    `volatile-lru`, so only expiring cache keys are evicted, never queued
    tasks.
  - Host preparation, first deployment, updates, restore and the
    format-change runbook are in `docs/deployment.md`.

### 3.3 Makefile (all commands run in containers)

| Target | Runs |
|---|---|
| `make up` / `make down` / `make logs` | dev stack lifecycle |
| `make build` | `docker compose build` |
| `make lock` | `uv lock` in a `uv` container |
| `make migrate` / `make makemigrations` | via `docker compose run --rm api` |
| `make shell` | `python manage.py shell` |
| `make bootstrap EMAIL=… HOUSEHOLD=…` | `bootstrap_household` |
| `make superuser` | `createsuperuser` |
| `make test [ARGS=…]` | `pytest` in the `api` container against the `db` service |
| `make lint` / `make fmt` | `ruff check` / `ruff format` |
| `make typecheck` | `mypy` (non-blocking at first) |
| `make check` | lint, format check, `makemigrations --check --dry-run`, tests |
| `make parse-receipt SRC=<url\|file>` | `parse_receipt` command |
| `make sanitize-fixture PROVIDER=… IN=… OUT=…` | `sanitize_fixture` command |
| `make prod-up` / `make prod-down` / `make prod-logs` / `make prod-ps` | production compose |
| `make prod-ca` | copies the proxy's local root CA certificate to `eksoda-root-ca.crt` |
| `make backup` / `make restore FILE=… CONFIRM=yes` | `pg_dump -Fc` in the `db` container into `BACKUP_DIR`. Restore takes a safety dump, stops the app services, drops and recreates the database, and runs `pg_restore --single-transaction` |
| `make <target> PROD=1` | Runs any target against the production compose files |

### 3.4 Environment variables (`.env.example`)

| Variable | Default (dev) | Purpose |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` | |
| `DJANGO_SECRET_KEY` | (generated, required in prod) | |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | admin behind the proxy |
| `DJANGO_ADMIN_PATH` | `admin/` | configurable admin path |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `eksoda` / `eksoda` / `eksoda` | |
| `DATABASE_URL` | `postgres://eksoda:eksoda@db:5432/eksoda` | |
| `REDIS_URL` | `redis://redis:6379` | broker uses db 0, cache uses db 1 |
| `JWT_SIGNING_KEY` | falls back to the secret key | |
| `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS` | `15` / `30` | |
| `REGISTRATION_OPEN` | `false` | D2 |
| `FETCH_CONNECT_TIMEOUT` / `FETCH_READ_TIMEOUT` / `FETCH_TOTAL_TIMEOUT` | `5` / `15` / `30` | seconds |
| `FETCH_MAX_BYTES` | `2097152` | |
| `IMPORT_TASK_RATE_LIMIT` | `30/m` | per worker |
| `THROTTLE_IMPORT_MINUTE` / `THROTTLE_IMPORT_DAY` / `THROTTLE_LOGIN` | `30/min` / `500/day` / `5/min` | |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `console` (prod: `json`) | |
| `SENTRY_DSN` / `SENTRY_ENVIRONMENT` / `SENTRY_RELEASE` | empty (disabled) / `production` / empty | |
| `THROTTLE_ADMIN_LOGIN` | `5/min` | admin login POSTs per IP |
| `DOMAIN` | empty | Caddy site address (prod): a local name such as `eksoda.lan` |
| `HTTP_PORT` / `HTTPS_PORT` | `80` / `443` | host ports of the proxy (prod) |
| `WEB_CONCURRENCY` / `CELERY_CONCURRENCY` | `2` / `1` | process counts (prod) |
| `BACKUP_DIR` / `BACKUP_HOUR_UTC` / `BACKUP_RETENTION_DAYS` | `./backups` / `1` / `30` | backup service (prod) |
| `RUN_LIVE_TESTS` | `0` | enables `-m live` tests |

## 4. Configuration

### 4.1 Settings modules

- **`base.py`**
  - `INSTALLED_APPS`: Django contrib (incl. `django.contrib.postgres`),
    `rest_framework`, `rest_framework_simplejwt.token_blacklist`,
    `django_filters`, `drf_spectacular`, `drf_spectacular_sidecar`,
    and the project apps.
  - `MIDDLEWARE`: `SecurityMiddleware`, `WhiteNoiseMiddleware`,
    `common.logging.RequestContextMiddleware`, sessions (admin only),
    `CommonMiddleware`, CSRF (admin only), auth, messages,
    `XFrameOptionsMiddleware`.
  - `AUTH_USER_MODEL = "accounts.User"`. `PASSWORD_HASHERS` puts
    `Argon2PasswordHasher` first. The four default password validators.
  - `USE_TZ = True`, `TIME_ZONE = "Europe/Athens"` (default display;
    storage is UTC).
  - `DATA_UPLOAD_MAX_MEMORY_SIZE = 16384`.
  - `CACHES`: `django.core.cache.backends.redis.RedisCache` on
    `REDIS_URL/1`. Throttles use it.
  - `REST_FRAMEWORK`:
    - authentication: `JWTAuthentication`
    - permissions: `IsAuthenticated`
    - pagination: `common.pagination.PageNumberPagination` (25, max 100)
    - filter backends: `DjangoFilterBackend`, `OrderingFilter`
    - exception handler: `common.errors.exception_handler`
    - schema class: `drf_spectacular.openapi.AutoSchema`
    - `COERCE_DECIMAL_TO_STRING = True`
    - throttle rates for `import_minute`, `import_day`, `login`
  - `SIMPLE_JWT`: lifetimes from env, `ROTATE_REFRESH_TOKENS = True`,
    `BLACKLIST_AFTER_ROTATION = True`, `UPDATE_LAST_LOGIN = True`,
    `AUTH_HEADER_TYPES = ("Bearer",)`, signing key from env.
  - `SPECTACULAR_SETTINGS`: title, version `1.0.0`, sidecar assets,
    `COMPONENT_SPLIT_REQUEST = True`, tags per app.
  - `CELERY_*`: see §12.7.
  - `LOGGING`: see §17.
- **`dev.py`:** `DEBUG = True`, console log format.
- **`test.py`:** MD5 hasher (speed), locmem cache, JSON logs captured,
  Celery not eager (tests call
  services directly or use `django_capture_on_commit_callbacks`).
- **`prod.py`:** `DEBUG = False`; `SECURE_PROXY_SSL_HEADER`;
  `SECURE_SSL_REDIRECT = False` (Caddy redirects); secure cookies;
  HSTS (1 year); a required-secret check at startup.

### 4.2 Application tunables

Tunables are plain Django settings in `base.py`, read where they are
used with `django.conf.settings` (so tests override them with the
`settings` fixture). There is no wrapper layer.

| Setting | Default | Used by |
|---|---|---|
| `REGISTRATION_OPEN` | env, `False` | `accounts.services.register_user` |
| `INVITATION_TTL_DAYS` | env, `7` | `households.services.create_invitation` |
| `FETCH_CONNECT_TIMEOUT`, `FETCH_READ_TIMEOUT`, `FETCH_TOTAL_TIMEOUT`, `FETCH_MAX_BYTES` | env, 5 s, 15 s, 30 s, 2 MiB | `receipts/conf.py` (builds `FetchLimits`) |
| `IMPORT_LEASE_SECONDS`, `IMPORT_RETRY_SCHEDULE` | constants: `300`; `(60, 300, 1800, 7200, 21600, 86400)` | `receipts.services.pipeline` |
| `IMPORT_TASK_RATE_LIMIT` | env, `30/m` | `receipts.tasks` |
| `MATCH_GUARD_SIMILARITY` | constant `0.4` (requirements §9.2) | `products.matching` |

## 5. Dependencies (`pyproject.toml`)

Exact versions are pinned in `uv.lock` during M1.

| Runtime | Constraint |
|---|---|
| `django` | `>=5.2,<5.3` (LTS) |
| `djangorestframework` | `>=3.16` |
| `django-filter` | `>=25.1` |
| `drf-spectacular[sidecar]` | `>=0.28` |
| `djangorestframework-simplejwt` | `>=5.5` |
| `psycopg[binary]` | `>=3.2` |
| `celery[redis]` | `>=5.5` |
| `django-environ` | `>=0.12` |
| `beautifulsoup4`, `lxml` | `>=4.13`, `>=5.3` |
| `urllib3`, `certifi` | `>=2.3`, latest |
| `argon2-cffi` | `>=23.1` |
| `whitenoise` | `>=6.8` |
| `python-json-logger` | `>=3.2` |
| `sentry-sdk` | `>=2.20` |
| `gunicorn` | `>=23` |

| Dev | |
|---|---|
| `pytest`, `pytest-django`, `pytest-cov` | test runner |
| `factory-boy` | factories |
| `ruff` | lint and format |
| `mypy`, `django-stubs`, `djangorestframework-stubs` | type checking |
| `watchfiles` | worker auto-reload in dev |

## 6. Common infrastructure (`apps/common`)

### 6.1 Base models and fields

```python
class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: abstract = True

class UUIDModel(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class Meta: abstract = True

# fields.py: the only money and quantity field factories
def MoneyField(**kw):     return models.DecimalField(max_digits=12, decimal_places=2, **kw)
def UnitPriceField(**kw): return models.DecimalField(max_digits=14, decimal_places=4, **kw)
def QuantityField(**kw):  return models.DecimalField(max_digits=14, decimal_places=4, **kw)
def NormQtyField(**kw):   return models.DecimalField(max_digits=16, decimal_places=6, **kw)
def RateField(**kw):      return models.DecimalField(max_digits=5,  decimal_places=2, **kw)
```

### 6.2 Error envelope (`common/errors.py`)

- `exception_handler(exc, ctx)` wraps DRF's handler and returns
  `{"error": {"code", "message", "details"}}`:
  - `ValidationError` → `code="validation_error"`, with the serializer
    errors in `details`.
  - `NotFound` and `Http404` → `not_found`.
  - `NotAuthenticated` and `AuthenticationFailed` →
    `not_authenticated`.
  - `Throttled` → `rate_limited`, keeping `Retry-After`.
  - Domain errors subclass `ApiError(APIException)` with a stable
    `default_code`, for example `UnsupportedProvider` (422),
    `HouseholdRequired` (400), `HouseholdForbidden` (403) and
    `NotRetryable` (409).
- Django's `handler500` returns the same JSON shape with
  `internal_error` and no details.
- Every error code is listed in one `ErrorCode` enum. The OpenAPI schema
  documents it as an enum.

### 6.3 Household context and scoping

```python
def resolve_household(request) -> Household:
    """X-Household-ID → that household if the user is a member (else HouseholdForbidden).
    No header → the only household; none → HouseholdForbidden;
    several → HouseholdRequired."""

class HouseholdScopedMixin:
    """Mixed into every household-scoped DRF view."""
    household_lookup = "household"            # e.g. "receipt__household" when there is no direct FK

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)          # auth and throttles first
        self.household = resolve_household(request)
        timezone.activate(ZoneInfo(self.household.timezone))   # datetimes in household tz

    def get_queryset(self):
        return self.scope_queryset(super().get_queryset(), self.household)
```

- Object lookups go through `get_queryset()`, so objects of another
  household always produce 404.
- `get_queryset()` calls `scope_queryset(queryset, household)`, which
  filters on `household_lookup` by default. Views over data a household
  reaches indirectly override it, never skip it: merchants and stores
  (through the household's receipts), categories (own plus system).
- `apps.common.schema.AutoSchema` documents the optional
  `X-Household-ID` header on every operation of these views.
- Owner-only actions (household routes take the household from the URL)
  call `households.services.require_owner(membership)`.
- Services take `household` as an explicit argument. They never read it
  from global state.
- `timezone.deactivate()` runs in `finalize_response`.

### 6.4 Text and number utilities (pure Python)

- `common/text.py`
  - `normalize_text(s) -> str`: the §9.5 pipeline.
  - `normalize_address(...)`.
  - `fingerprint(s) -> str`: SHA-256 hex.
  - The look-alike map is a frozen dict of 14 Latin↔Greek capital
    pairs. A token's script is decided by its majority script.
- `common/numbers.py`
  - `Culture = Literal["el", "en"]`
  - `parse_decimal(text, culture) -> Decimal`: strict regexes per
    culture, optional leading `-`, optional trailing `%`. Raises
    `NumberFormatError`.
  - `parse_local_datetime(text, culture, tz) -> datetime`: `el` handles
    `dd/mm/yyyy h:mm π.μ.|μ.μ.`, `en` handles `AM|PM`. Returns an aware
    datetime with `fold=0`.
  - `parse_local_date(text) -> date`.

## 7. Accounts and households

### 7.1 Models

```python
class User(AbstractBaseUser, PermissionsMixin, UUIDModel):
    email = models.EmailField(max_length=254)
    display_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    USERNAME_FIELD = "email"
    objects = UserManager()                     # lowercases email on create
    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="uniq_user_email_ci")]

class Household(UUIDModel):
    name = models.CharField(max_length=120)
    default_currency = models.CharField(max_length=3, default="EUR")
    timezone = models.CharField(max_length=64, default="Europe/Athens")   # validated by zoneinfo

class HouseholdMember(UUIDModel):
    class Role(models.TextChoices): OWNER = "owner"; MEMBER = "member"
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices)
    joined_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["household", "user"], name="uniq_member")]

class HouseholdInvitation(UUIDModel):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="invitations")
    code_hash = models.CharField(max_length=64, unique=True)    # sha256(code)
    role = models.CharField(max_length=10, choices=HouseholdMember.Role.choices, default="member")
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    expires_at = models.DateTimeField()
    accepted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
```

### 7.2 Flows

- **Invitation code:** `secrets.token_urlsafe(12)` (about 96 bits). It is
  returned once and stored as SHA-256. A plain hash is enough because
  the code is high-entropy and random.
- **Register** (`POST /auth/register`), all in one transaction:
  - With `invite_code`: look up the invitation by hash with
    `select_for_update()`. It must not be expired, revoked or accepted.
    Create the user and the membership, then mark the invitation
    accepted.
  - Without a code, and `REGISTRATION_OPEN`: create the user and a
    household named "{display_name or email local part}'s household",
    with the user as owner.
  - Otherwise: `400 invite_required`.
  - The response contains the user, memberships and a token pair, so the
    app can log in immediately.
- **Join** (`POST /households/join`): the same invitation checks for an
  existing user. Already a member → `409 already_member`.
- **Login:** simplejwt's `TokenObtainPairView` with a serializer that
  lowercases the email. `LoginRateThrottle` keys the cache on
  `ip + sha256(email)`.
- **Logout:** blacklists the given refresh token.
- **Password change:** checks the old password and validates the new
  one, then blacklists every outstanding refresh token of the user.
- **Membership removal:** removing the last owner returns
  `409 last_owner`.
- **`bootstrap_household --email --household [--password-env VAR]`:**
  idempotent. It creates the user (password from the env var, or a
  prompt), the household and the owner membership.

## 8. Data model (Django)

Notation: `FK(target, on_delete)`. All models extend `UUIDModel` unless
noted otherwise. Choices are `TextChoices` defined next to each model.

### 8.1 Merchants (`apps/merchants/models.py`)

```python
class Merchant(UUIDModel):
    country_code = CharField(2, default="GR")
    vat_number = CharField(20)                    # digits only, no "EL"
    legal_name = CharField(255)
    display_name = CharField(120)
    activity_description = TextField(blank=True)
    tax_office = CharField(120, blank=True)
    gemi_number = CharField(32, blank=True)
    street = CharField(255, blank=True); street_number = CharField(20, blank=True)
    city = CharField(120, blank=True); postal_code = CharField(10, blank=True)
    details_as_of = DateTimeField(null=True)      # issue time of the receipt that set the details
    default_category = FK("products.ProductCategory", SET_NULL, null=True, blank=True,
                          limit_choices_to={"household__isnull": True})   # added in M4
    Meta.constraints = [UniqueConstraint(fields=["country_code", "vat_number"], name="uniq_merchant_vat")]

class Store(UUIDModel):
    merchant = FK(Merchant, PROTECT, related_name="stores")
    branch_number = CharField(16, null=True, blank=True)
    display_name = CharField(120, blank=True)
    street = CharField(255, blank=True); city = CharField(120, blank=True)
    postal_code = CharField(10, blank=True); country_code = CharField(2, default="GR")
    normalized_address = CharField(400, blank=True)   # street, number, postal code, city
    details_as_of = DateTimeField(null=True)
    Meta.constraints = [
        UniqueConstraint(fields=["merchant", "branch_number"],
                         condition=Q(branch_number__isnull=False), name="uniq_store_branch"),
        UniqueConstraint(fields=["merchant", "normalized_address"],
                         condition=Q(branch_number__isnull=True) & ~Q(normalized_address=""),
                         name="uniq_store_address"),
    ]
```

`merchants.services.resolve_merchant()` and `resolve_store()` take the
canonical `Party` and `Branch`. Details are refreshed from receipts: an
empty field is filled from any receipt; a filled field only from a
receipt issued at the same time or later than `details_as_of`, and
never by a truncated copy of itself.

### 8.2 Receipts (`apps/receipts/models.py`)

```python
class ReceiptImportJob(UUIDModel):
    class Status(TextChoices): PENDING, COMPLETED, FAILED
    class Outcome(TextChoices): CREATED, DUPLICATE, RECEIPT_DELETED
    household = FK(Household, CASCADE, related_name="import_jobs")
    requested_by = FK(User, SET_NULL, null=True)
    provider_code = CharField(32)
    url_identity = CharField(200)                 # "GR:094062259:FA83…029F"
    submitted_url = TextField()                   # canonical form, sensitive
    url_fingerprint = CharField(64, db_index=True)
    issuer_vat = CharField(20, blank=True)        # from the URL (Impact) or the parsed receipt
    status = CharField(10, choices=Status.choices, default=PENDING)
    outcome = CharField(20, choices=Outcome.choices, null=True, blank=True)
    attempt_count = PositiveSmallIntegerField(default=0)   # reset on manual retry
    next_attempt_at = DateTimeField(null=True, blank=True)  # due time, also the claim lease
    last_error_code = CharField(40, blank=True)
    last_error_message = CharField(255, blank=True)
    receipt = FK("receipts.Receipt", SET_NULL, null=True, blank=True, related_name="import_jobs")
    finished_at = DateTimeField(null=True, blank=True)
    Meta.constraints = [
        UniqueConstraint(fields=["household", "provider_code", "url_identity"], name="uniq_job_identity"),
        CheckConstraint(name="job_outcome_iff_completed", condition=
            Q(status="completed", outcome__isnull=False) | (~Q(status="completed") & Q(outcome__isnull=True))),
    ]
    Meta.indexes = [Index(fields=["status", "next_attempt_at"]), Index(fields=["household", "-created_at"])]
```

`Receipt` has no 1:1 back to the job. Several jobs (different URL forms)
can resolve to the same receipt through the `duplicate` outcome.

```python
class Receipt(UUIDModel):
    class Kind(TextChoices): SALE, CREDIT_NOTE, OTHER
    class Status(TextChoices): ACTIVE, CANCELLED
    class PaymentMethod(TextChoices): CARD, CASH, BANK, MIXED, OTHER, UNKNOWN

    household = FK(Household, CASCADE, related_name="receipts")
    imported_by = FK(User, SET_NULL, null=True)
    merchant = FK(Merchant, PROTECT); store = FK(Store, PROTECT, null=True, blank=True)
    provider_code = CharField(32); parser_version = CharField(20)
    issuer_country = CharField(2); issuer_vat = CharField(20)
    uid = CharField(64, null=True, blank=True)
    mark = CharField(32, null=True, blank=True); cancellation_mark = CharField(32, null=True, blank=True)
    source_key = CharField(80, null=True, blank=True)   # identity without MARK/UID (M2b)
    document_kind = CharField(12, choices=Kind.choices)
    document_type_code = CharField(8, null=True, blank=True)
    document_number = CharField(100, blank=True)        # canonical formatted_number, else series + number
    issued_at = DateTimeField()
    currency = CharField(3, default="EUR")
    gross_total = MoneyField()
    net_total = MoneyField(null=True); vat_total = MoneyField(null=True)
    discount_total = MoneyField(null=True)
    payment_method = CharField(10, choices=PaymentMethod.choices, default=UNKNOWN)
    status = CharField(10, choices=Status.choices, default=ACTIVE)
    validation_warnings = JSONField(default=list, blank=True)
    excluded_from_analytics = BooleanField(default=False)
    user_note = TextField(blank=True)
    source_url = TextField(); source_url_fingerprint = CharField(64)
    source_data = JSONField(default=dict)               # canonical.to_json() minus source_url
    Meta.constraints = [
        UniqueConstraint(fields=["household", "mark"], condition=Q(mark__isnull=False), name="uniq_receipt_mark"),
        UniqueConstraint(fields=["household", "issuer_country", "issuer_vat", "uid"],
                         condition=Q(uid__isnull=False), name="uniq_receipt_uid"),
        UniqueConstraint(fields=["household", "source_key"],
                         condition=Q(source_key__isnull=False), name="uniq_receipt_source_key"),
    ]
    Meta.indexes = [Index(fields=["household", "-issued_at"]),
                    Index(fields=["household", "merchant", "issued_at"])]

class ReceiptItem(UUIDModel):
    class LineType(TextChoices): PRODUCT, DISCOUNT, FEE, OTHER
    class Unit(TextChoices): PIECE, KG, L, OTHER
    class MatchStatus(TextChoices): MATCHED, NEEDS_REVIEW, NOT_A_PRODUCT

    receipt = FK(Receipt, CASCADE, related_name="items")
    household = FK(Household, CASCADE)           # denormalized; set by the service only
    line_number = PositiveIntegerField()
    line_type = CharField(10, choices=LineType.choices)
    description = TextField(); normalized_description = TextField(blank=True)   # never cut
    merchant_product_code = CharField(100, null=True, blank=True)
    quantity = QuantityField(null=True); unit = CharField(6, choices=Unit.choices, null=True)
    unit_price = UnitPriceField(null=True)
    gross_amount = MoneyField()                  # after any line discount
    net_amount = MoneyField(null=True); vat_rate = RateField(null=True); vat_amount = MoneyField(null=True)
    discount_amount = MoneyField(null=True)
    # RESTRICT, not PROTECT: deleting a household deletes its products and lines together
    product = FK("products.Product", RESTRICT, null=True, blank=True,
                 related_name="receipt_items")
    match_status = CharField(14, choices=MatchStatus.choices)
    normalized_quantity = NormQtyField(null=True)
    normalized_unit = CharField(6, choices=NormalizedUnit.choices, null=True)   # kg | l | piece | other
    normalized_unit_price = UnitPriceField(null=True)
    user_note = TextField(blank=True)
    Meta.constraints = [
        UniqueConstraint(fields=["receipt", "line_number"], name="uniq_item_line"),
        CheckConstraint(name="item_product_iff_matched", condition=
            Q(product__isnull=False, match_status="matched") |
            Q(product__isnull=True, match_status__in=["needs_review", "not_a_product"])),
        CheckConstraint(name="item_not_a_product_iff_non_product", condition=
            Q(line_type="product", match_status__in=["matched", "needs_review"]) |
            Q(~Q(line_type="product"), match_status="not_a_product")),
    ]
    Meta.indexes = [Index(fields=["household", "match_status"]), Index(fields=["product"])]
```

The detailed myDATA amounts (withheld, fees, other taxes, stamp duty,
digital fee, deductions), the VAT breakdown, payments, coverage,
notices and raw line values live in `Receipt.source_data`. The API
reads coverage and the VAT breakdown from there. A value moves to a
column only when a filter or an aggregate needs it.

### 8.3 Products (`apps/products/models.py`)

```python
class ProductCategory(UUIDModel):
    household = FK(Household, CASCADE, null=True, blank=True)    # null = system
    name = CharField(80); slug = SlugField(80)
    Meta.constraints = [UniqueConstraint(fields=["household", "slug"],
                        nulls_distinct=False, name="uniq_category_slug")]

class Product(UUIDModel):
    class PackageUnit(TextChoices): G, KG, ML, CL, L, PIECE
    household = FK(Household, CASCADE, related_name="products")
    name = CharField(255); normalized_name = CharField(255)   # set from name in save()
    brand = CharField(120, blank=True)
    category = FK(ProductCategory, SET_NULL, null=True, blank=True)
    package_quantity = QuantityField(null=True, blank=True)
    package_unit = CharField(6, choices=PackageUnit.choices, null=True, blank=True)
    Meta.constraints = [
        CheckConstraint(name="product_package_complete", condition=
            Q(package_quantity__isnull=True, package_unit__isnull=True) |
            Q(package_quantity__isnull=False, package_unit__isnull=False, package_quantity__gt=0)),
    ]
    Meta.indexes = [Index(fields=["household", "name"])]

class MerchantProductMapping(UUIDModel):
    household = FK(Household, CASCADE); merchant = FK(Merchant, PROTECT)
    merchant_product_code = CharField(100, null=True, blank=True)   # as on ReceiptItem
    normalized_description = TextField(); last_seen_description = TextField()  # never cut
    product = FK(Product, CASCADE, related_name="mappings")
    Meta.constraints = [
        UniqueConstraint(fields=["household", "merchant", "merchant_product_code"],
                         condition=Q(merchant_product_code__isnull=False), name="uniq_mapping_code"),
        UniqueConstraint(fields=["household", "merchant", "normalized_description"],
                         condition=Q(merchant_product_code__isnull=True), name="uniq_mapping_desc"),
    ]
```

### 8.4 Migrations

| Migration | Contents |
|---|---|
| `common/0001` (M1, exists) | `CREATE EXTENSION IF NOT EXISTS pg_trgm` and `unaccent`. Kept, but unused until fuzzy search is needed (D15) |
| `merchants/0001`, `receipts/0001` (M3) | Merchants, stores, import jobs, receipts, lines |
| `products/0001` (M4) | Categories, products, mappings |
| `products/0002_seed_categories` (M4) | Data migration with the system categories (requirements §8.9). Idempotent by slug |
| `merchants/0002`, `receipts/0002` (M4) | `Merchant.default_category`; `ReceiptItem.product`, the normalized-price columns and `item_product_iff_matched` |

## 9. Provider layer (`apps/receipts`)

### 9.1 Canonical types (`canonical.py`)

All types are `@dataclass(frozen=True, slots=True)`. Amounts are
`Decimal`, and tuples are used instead of lists.

```python
class Address:      street: str | None; number: str | None; city: str | None; postal_code: str | None; country: str | None
class Party:        country_code: str; vat_number: str; legal_name: str; activity: str | None
                    tax_office: str | None; gemi_number: str | None; address: Address | None
class Branch:       number: str | None; address: Address | None
class Document:     type_code: str; type_label: str | None; series: str | None; number: str | None
                    formatted_number: str | None; issued_at: datetime; issued_date: date; currency: str
class Identity:     uid: str; mark: str | None; cancellation_mark: str | None; transmission_failure: bool
class Totals:       gross: Decimal; net: Decimal | None; vat: Decimal | None; withheld: Decimal | None
                    fees: Decimal | None; other_taxes: Decimal | None; stamp_duty: Decimal | None
                    digital_fee: Decimal | None; deductions: Decimal | None
class VatEntry:     category_code: str | None; rate: Decimal | None; net: Decimal; vat: Decimal
class Payment:      method_code: str | None; method_label: str | None; amount: Decimal; tip: Decimal
class Line:         line_number: int; line_type_code: str | None; annotation_code: str | None
                    merchant_product_code: str | None; barcode: str | None; description: str
                    quantity: Decimal; unit_code: str | None; unit_label: str | None
                    unit_price: Decimal | None; unit_price_basis: Literal["gross", "net", "unknown"]
                    net: Decimal | None; vat_category_code: str | None; vat_rate: Decimal | None
                    vat: Decimal | None; withheld: Decimal | None; fees: Decimal | None
                    other_taxes: Decimal | None; stamp_duty: Decimal | None; digital_fee: Decimal | None
                    deductions: Decimal | None; gross: Decimal; discount: Decimal | None
                    vat_exemption_code: str | None; raw: Mapping[str, str]
class CanonicalReceipt:
    provider_code: str; parser_version: str; culture: str; source_url: str
    issuer: Party; branch: Branch | None; document: Document; identity: Identity
    totals: Totals; vat_breakdown: tuple[VatEntry, ...]; payments: tuple[Payment, ...]
    lines: tuple[Line, ...]; provider_payload: Mapping[str, Any]; unknown_fields: Mapping[str, str]
    def to_json(self) -> dict: ...    # Decimal → str, datetime → ISO. Used by parse_receipt and tests
```

### 9.2 myDATA code tables (`mydata.py`, provider-neutral)

| Function | Maps |
|---|---|
| `document_kind(type_code) -> Kind` | `11.4` and other credit types → `CREDIT_NOTE`; `11.1`, `11.2`, `11.3`, `11.5` and invoice types → `SALE`; else `OTHER` |
| `vat_rate(category_code) -> Decimal \| None` | VAT category code → rate |
| `measurement_unit(code) -> Unit` | `1` → `PIECE`, `2` → `KG`, `3` → `L` (the only codes in the official v1.0.9 table), anything else → `OTHER` |
| `payment_method(code) -> PaymentMethod` | `7` (POS / e-POS) → `CARD`, `3` → `CASH`, `1`, `2`, `6`, `8` → `BANK`, others → `OTHER` |

The tables are checked against the official AADE myDATA documentation
during M2. Unknown codes never raise: they map to `OTHER`/`None`, the
raw code is kept, and a warning is logged with the provider and code.

### 9.3 URL parsing and registry

```python
@dataclass(frozen=True)
class ParsedUrl:
    scheme: str; host: str; port: int | None; path: str; query: str; raw: str

def parse_submitted_url(raw: str) -> ParsedUrl:
    """strip(); at most 2048 chars; urlsplit; scheme https; no userinfo; port None or 443;
    host lowercased and IDNA-encoded; no fragment. Raises InvalidUrl."""

@dataclass(frozen=True)
class UrlIdentity:
    provider_code: str; identity: str; canonical_url: str
    issuer_country: str; issuer_vat: str; uid: str

@dataclass
class Provider:                 # one per source, built in providers/<code>/__init__.py
    code: str; hosts: frozenset[str]; layouts: Sequence[Layout]
    recognize; parse_html; sanitize; fetch_document = None   # functions of the provider's modules
    def fetch(self, identity, fetcher) -> FetchedDocument      # one GET unless fetch_document is set
    def parse(self, doc, identity) -> CanonicalReceipt

class ProviderRegistry:
    def __init__(self, providers: Iterable[Provider])          # duplicate codes/hosts → ValueError
    def resolve_url(self, raw: object) -> tuple[Provider, UrlIdentity]
        # InvalidUrl; unknown host → UnsupportedProvider; recognize() is None → UnsupportedUrlFormat
    def get(self, code: str) -> Provider

registry = ProviderRegistry([impact.provider, entersoft.provider, aade_fhm.provider])
```

**Impact recognition:** `^/p/([A-Z]{2})(\d{9})/([0-9A-F]{40})/([0-9A-F]{32})/?$`,
matched case-insensitively. A non-empty query string means
`UnsupportedUrlFormat` (strict now; relax only with evidence). The
canonical URL is `https://einvoice.impact.gr/p/EL{vat}/{UID}/{GUID}`
with uppercase hex. The identity is `"{GR}:{vat}:{UID}"`; the `EL`
prefix maps to country `GR`. The URL fingerprint is the SHA-256 of the
canonical URL.

### 9.4 Provider errors

```python
class RetryPolicy(Enum): TRANSIENT; NOT_FOUND; INTERNAL; NONE

class ReceiptError(Exception):
    code: ErrorCode; retry: RetryPolicy; public_message: str
class ProviderUnreachable(ReceiptError):     code=provider_unreachable;    retry=TRANSIENT
class ProviderTimeout(ReceiptError):         code=provider_timeout;        retry=TRANSIENT
class ProviderHttpError(ReceiptError):       code=provider_error;          retry=TRANSIENT   # 408/429/5xx
class BlockedDestination(ReceiptError):      code=blocked_destination;     retry=NONE
class ResponseTooLarge(ReceiptError):        code=response_too_large;      retry=NONE
class UnexpectedContentType(ReceiptError):   code=unexpected_content_type; retry=NONE
class ReceiptNotFound(ReceiptError):         code=receipt_not_found;       retry=NOT_FOUND
class FormatChanged(ReceiptError):           code=provider_format_changed; retry=NONE      # incl. 3xx, other 4xx
class InconsistentSource(ReceiptError):      code=inconsistent_source;     retry=NONE
```

Each error carries an internal `detail` string for logs and Sentry. The
API only ever shows `public_message`.

### 9.5 Impact adapter (`providers/impact/`)

| File | Contents |
|---|---|
| `__init__.py` | `provider` (code `impact`, host `einvoice.impact.gr`); `PARSER_VERSION = "impact/1"` is in `parser.py` |
| `urls.py` | Recognition regex and canonicalization (§9.3) |
| `labels.py` | Known commercial field names, tax-view label → key maps (Greek in every culture), drop lists |
| `views.py` | `extract_commercial()` → `CommercialView` and `extract_tax_view()` → `TaxView` (plain string maps) |
| `parser.py` | `parse_html(html, identity) -> CanonicalReceipt`: page classification, culture, cross-checks, build |
| `sanitize.py` | Fixture sanitizer used by the `sanitize_fixture` command |

As built in M2, the shared pure modules are: `receipts/links.py`
(`ParsedUrl`, `parse_submitted_url`), `receipts/errors.py` (error
codes, retry policies, exception hierarchy), and
`receipts/providers/__init__.py` (`registry`).
`receipts/conf.py` builds `FetchLimits` from settings.

**Parse algorithm**

1. `soup = BeautifulSoup(body, "lxml")`, decoded from the `Content-Type`
   charset (default UTF-8).
2. `classify_page(soup)`:
   - `div.invoice` and `div.InvoicesDocDetailed` both present →
     `RECEIPT`.
   - The text contains "Document with UniqueId" and there is no invoice
     → `NOT_FOUND` (raise `ReceiptNotFound`).
   - Anything else → raise `FormatChanged("unknown page")`.
3. **Culture** comes from `div.invoice[data-culture]` (`el` or `en`).
   Anything else is `FormatChanged`. Tax-view labels are Greek in both
   cultures, so only number and date formats depend on it. The date
   order is fixed per (culture, view): `en` tax-view dates are
   month/day.
4. **Commercial view:** fields are found with
   `select_one(".field-<Name> .value")` inside their section.
   - `#header` is walked in document order. A repeated address field
     (`Street`, `City`, `Postal`, `Country`) starts a new address block.
     Block 1 is the head office, block 2 is the branch.
   - Detail rows come from `.section-details tr` that contain
     `td.field-Code` or `td.field-Description1`.
   - `CounterParty` and `field-TransactionId` are **never read**.
5. **Tax view:**
   - `.InvoiceHeader`, `.InvoiceSummary` and `.PaymentMethodType` tables
     are read as label → value maps.
   - Each `.InvoiceLines` table is one line.
   - Labels are normalized (whitespace collapsed) and mapped through
     `labels.py`. Unmapped labels go to `unknown_fields` with the
     section prefix.
   - Personal-data labels (payment unique ID, POS terminal ID,
     signatures, provider authentication string) are in an explicit
     **drop** list. They are skipped without being stored.
6. **Required fields** (missing → `FormatChanged`): issuer VAT, UID,
   document type, issue date, gross total, at least one line, and net,
   VAT and gross on every line. The MARK is also required unless the
   transmission-failure flag is `1`.
7. **Cross-checks** (any mismatch → `InconsistentSource`):
   - The page UID and VAT equal the URL identity.
   - The receipt URL shown in the tax view equals the canonical URL
     (compared case-insensitively).
   - Line counts are equal.
   - Per line, net, VAT and gross agree between the two views.
   - The summary totals agree.
8. **Build the `CanonicalReceipt`:**
   - `issued_at` comes from the commercial date and time. Its date must
     equal the tax-view date, otherwise `InconsistentSource`.
   - `unit_price_basis = "gross"`.
   - The VAT rate comes from the commercial `VatCategory`. It must equal
     `mydata.vat_rate(code)` when the code is known, otherwise
     `InconsistentSource`.
   - A cancellation MARK of `"0"` or empty becomes `None`.
   - `provider_payload` is an allowlisted dict of the extracted values
     (as strings), plus `unknown_fields`.

### 9.6 Commands

- `parse_receipt <url|path> [--json] [--culture-check]`: runs the
  provider (with the safe fetcher for URLs) and prints the canonical
  JSON and validation issues. It never touches the database. URLs are
  printed masked.
- `parse_receipt` finds a saved page's URL from `--url`, else from a
  sibling `<page>.meta.json`, else from the first link on the page that
  a registered provider recognizes.
- `sanitize_fixture <provider> <in.html> <out.html>`: runs that
  provider's sanitizer. Personal values and tokens become deterministic
  fakes of the same shape (digits → 0, letters → X/x; access GUIDs and
  UUIDs → zeros). Merchant data is kept. Nothing is written if any
  original value survives (`providers/sanitizing.finish` verifies it).

### 9.7 Built for new formats (M2b)

| Mechanism | Where | Purpose |
|---|---|---|
| Layouts | `Layout` protocol and `parse_with_layouts` in `providers/base.py`. Each provider has `LAYOUTS` (newest first) | A changed page gets a new layout; old fixtures keep passing. `parser_version` is the layout name |
| Shared vocabularies | `receipts/vocabulary.py` | Label → value maps (document types, units, payment methods, currencies, rate → VAT category), compared after `normalize_text` (so `ΤΕΜΑΧΙΟ` = `TEMAXIO`). Unknown labels become drift, not errors |
| Coverage | `canonical.Coverage` | Each receipt states what its source provides. Validation rules adapt (R7, R11, line rules) |
| Notices | `canonical.Notice` | Provider-detected conditions (e.g. `signature_mismatch`) become warnings |
| HTML helpers | `providers/html.py` | `label_map`, `key_of`, `amount` (strips currency markers), `required`, `child_cells` |
| Sanitizer framework | `providers/sanitizing.py` | `Secrets` collection, `strip_active_content`, `finish` (replace + verify). Each provider has `sanitize()` |
| Provider status handling | `SafeFetcher.get(accept_statuses=…)` | Providers interpret odd statuses (Entersoft answers 418 for unknown documents) |
| Follow-up requests | Entersoft `fetch()` | Same host only, and the framed document must have the same ids (otherwise `inconsistent_source`) |
| Fixture harness | `tests/receipts/test_fixtures.py` | Every `tests/fixtures/<provider>/<name>.meta.json` is a golden test. No test code is needed per receipt |
| Runbook | `docs/deployment.md` §8 | The procedure for a new source, a new layout or a changed page |

**Providers as built:**

| Code | Host | Fetch | Layout | Coverage |
|---|---|---|---|---|
| `impact` | `einvoice.impact.gr` | 1 request | `impact/1`: two views, cross-checked | full |
| `entersoft` | `e-invoicing.gr` | shell page, then the framed `/api/GetInvoice` document (418 means not found) | `entersoft/1`: single view; Σ lines, discounts and VAT analysis enforced | no line net/VAT; codes derived from labels; time approximate (transmission time) |
| `aade_fhm` | `www1.aade.gr` | 1 request (`?SIG=`) | `aade_fhm/1`: AADE record table; alerts become notices | summary only (no lines, no MARK); `source_key` identity |

## 10. SSRF-safe fetcher (`receipts/fetching.py`)

```python
@dataclass(frozen=True)
class FetchLimits:
    connect_timeout: float = 5.0; read_timeout: float = 15.0
    total_timeout: float = 30.0; max_bytes: int = 2 * 1024 * 1024

@dataclass(frozen=True)
class FetchedDocument:
    body: bytes; status: int = 200; charset: str = "utf-8"
    def text(self) -> str

class SafeFetcher:
    def __init__(self, limits: FetchLimits, *, resolver=socket.getaddrinfo,
                 pool_factory=https_pool, clock=time.monotonic): ...
    def get(self, url: ParsedUrl, *, allowed_hosts: frozenset[str],
            accept_statuses: frozenset[int] = frozenset()) -> FetchedDocument: ...
```

**`get()` algorithm**

1. `url.scheme == "https"`, `url.host in allowed_hosts`,
   `url.port in (None, 443)`. Anything else → `BlockedDestination`.
2. `infos = resolver(host, 443, type=SOCK_STREAM)`, deduplicated.
   No address → `ProviderUnreachable`.
3. For each address, `ip = ip_address(addr)`, unwrapping
   `ip.ipv4_mapped`. If any address is not `ip.is_global`, or is
   multicast or unspecified, raise `BlockedDestination`. Being strict
   about *any* address means a mixed DNS answer is never accepted.
4. The pool is created for the **first validated IP**:
   `HTTPSConnectionPool(ip, 443, server_hostname=host,
   assert_hostname=host, cert_reqs="CERT_REQUIRED",
   ca_certs=certifi.where(), timeout=Timeout(connect, read),
   retries=False, maxsize=1)`. TLS SNI and certificate checks use the
   hostname while the TCP connection goes to the pinned IP. This
   defeats DNS rebinding.
5. `pool.urlopen("GET", path, headers=FIXED_HEADERS | {"Host": host},
   redirect=False, preload_content=False, decode_content=True)`.
   - `FIXED_HEADERS`: `User-Agent`, `Accept: text/html`,
     `Accept-Language: el-GR,el;q=0.9`, `Accept-Encoding: gzip`.
   - No cookies or auth headers.
   - urllib3 does not read proxy environment variables.
6. Status mapping:
   - 200 → continue
   - 404 → `ReceiptNotFound`
   - 408, 429, 5xx → `ProviderHttpError`
   - 3xx and other codes → `FormatChanged("unexpected status")`
7. `Content-Type` must start with `text/html`, otherwise
   `UnexpectedContentType`. A `Content-Length` above `max_bytes` is
   rejected early (`ResponseTooLarge`).
8. Stream with `resp.stream(64 KiB)`, counting **decompressed** bytes
   (`ResponseTooLarge` above the cap) and checking a monotonic deadline
   after each chunk (`ProviderTimeout`).
9. urllib3 exceptions map as follows: `ConnectTimeoutError` and
   `ReadTimeoutError` → `ProviderTimeout`; `NewConnectionError`,
   `ProtocolError` and `SSLError` → `ProviderUnreachable` (TLS errors
   are logged distinctly).

`pool_factory` and `resolver` are injectable, so every rule can be
unit-tested without network access.

## 11. Validation (`receipts/validation.py`)

```python
@dataclass(frozen=True)
class ValidationIssue:
    code: str; message: str; line_number: int | None = None
    expected: str | None = None; actual: str | None = None

def validate(receipt: CanonicalReceipt) -> list[ValidationIssue]: ...
```

- Implements R4–R12 (§10.2) as small rule functions over the canonical
  receipt. Missing optional amounts count as `0` in the sums.
- R1–R3 are fatal and live in the provider (§9.5), because they depend
  on provider structure.
- Tolerances are constants in one place:
  `LINE_TOL = Decimal("0.01")`, `TOTAL_TOL = Decimal("0.02")`.
- The result is stored as a list of dicts in
  `Receipt.validation_warnings`. An empty list means no warnings; there
  is no separate status column.

## 12. Import pipeline (`receipts/services/`, `receipts/tasks.py`)

### 12.1 Submission (`services/imports.py`)

```python
@dataclass(frozen=True)
class SubmitResult:
    job: ReceiptImportJob; created: bool; requeued: bool

def submit_import(*, user, household, raw_url: str) -> SubmitResult:
```

1. `parse_submitted_url()` → `registry.resolve()`. An
   `UnsupportedProvider` error is logged with the host only, then
   propagates (422).
2. In `transaction.atomic()`, try to create the job in a savepoint
   (`status=PENDING`, `next_attempt_at=now()`). An `IntegrityError` on
   `uniq_job_identity` means the job already exists: load it.
3. If the existing job is `failed`, or its outcome is
   `receipt_deleted`, requeue it: `status=PENDING`, `attempt_count=0`,
   `next_attempt_at=now()`, clear the error and outcome, store the
   newly submitted link (it may work where the old one did not),
   `requeued=True`. This update is a conditional `UPDATE … WHERE
   status IN (…)`, so it never waits on a worker that holds the row.
   `retry_import()` (API and admin) uses the same update for `failed`
   jobs only.
4. If the job was created or requeued:
   `transaction.on_commit(lambda: process_import.delay(job.id))`.
5. The view maps the result to `202` (created or requeued) or `200`
   (existing). `duplicate = not created`.

### 12.2 Processing (`services/pipeline.py`)

```python
def process_import(job_id: UUID) -> None:
    job = claim(job_id)                       # short transaction; None if not pending and due
    if job is None: return
    try:
        provider, identity = registry.resolve(parse_submitted_url(job.submitted_url))
        doc = provider.fetch(identity, fetcher)
        canonical = provider.parse(doc, identity)
        issues = validate(canonical)
        with transaction.atomic():
            receipt, outcome = persist(job, canonical, issues)
            complete(job, receipt, outcome)   # UPDATE … WHERE id = … AND status = 'pending'
    except ReceiptError as exc:
        record_failure(job, exc)
    except JobChanged:                        # complete() found the job no longer pending
        return                                # the receipt was rolled back
    except Exception as exc:                  # incl. SoftTimeLimitExceeded
        log.exception(...); sentry            # tracebacks are URL-redacted (§16)
        record_failure(job, InternalError(type(exc).__name__))   # never the message
```

**`claim()`**, in `transaction.atomic()`:

```python
job = (ReceiptImportJob.objects.select_for_update(skip_locked=True)
       .filter(id=job_id, status=PENDING, next_attempt_at__lte=now()).first())
if job is None: return None
if job.attempt_count > len(settings.IMPORT_RETRY_SCHEDULE):  # every attempt so far killed the worker
    mark_failed(job, InternalError("attempts exhausted")); return None
job.attempt_count += 1
job.next_attempt_at = now() + timedelta(seconds=settings.IMPORT_LEASE_SECONDS) # lease: a crashed worker's job is due again later
job.save(update_fields=[...])
```

The lease is the only protection needed against two workers running
the same job: a second claim finds the job not due. The hard time limit
(90 s) is far below the lease (5 min). `complete()` and
`record_failure()` only update rows that are still `pending`, and the
database constraints remain the final guard against a second receipt.

### 12.3 State transitions

| From | To | Trigger |
|---|---|---|
| — | `pending` | submit (new) |
| `failed`, or `completed` with `receipt_deleted` | `pending` | resubmit or manual retry (`attempt_count` reset) |
| `pending` | `pending` | claim (lease) or retryable error (next attempt scheduled) |
| `pending` | `completed` | persisted (same transaction as the receipt) |
| `pending` | `failed` | non-retryable error or schedule used up |

### 12.4 Failure handling

**`record_failure(job, exc)`**, in a short transaction:

```python
retryable = exc.retry in (RetryPolicy.TRANSIENT, RetryPolicy.NOT_FOUND)
step = job.attempt_count - 1                       # index into the schedule
job.last_error_code, job.last_error_message = exc.code, exc.public_message
if retryable and step < len(settings.IMPORT_RETRY_SCHEDULE):
    job.next_attempt_at = now() + timedelta(seconds=settings.IMPORT_RETRY_SCHEDULE[step] * uniform(0.9, 1.1))
else:
    job.status, job.finished_at, job.next_attempt_at = FAILED, now(), None
```

`RetryPolicy.INTERNAL` is no longer retried automatically; M3 may
collapse `RetryPolicy` to a boolean.

Retries are **not** scheduled with Celery `countdown`/`eta`. With a
Redis broker, ETA messages longer than the visibility timeout get
redelivered. Instead, `run_due_imports` (beat, every 60 s) enqueues
`pending` jobs whose `next_attempt_at` has passed. The database is the
scheduler.

### 12.5 Persistence (`services/persistence.py`)

All of this runs inside the pipeline's transaction:

1. **Merchant:** `get_or_create(country_code, vat_number)` with
   defaults from `canonical.issuer`. An existing merchant has its public
   fields refreshed when they differ (legal name, address, activity).
   `display_name` changes only if it still equals the derived default.
   `display_name` is derived from the legal name: the text before the
   first legal-form token (`ΑΕ`, `ΑΕΒΕ`, `ΙΚΕ`, `ΟΕ`, `ΕΕ`, …),
   title-cased. For example `METRO ΑΕΒΕ …` becomes `Metro`.
2. **Store:**
   - With a branch number: `get_or_create(merchant, branch_number)`,
     address refreshed.
   - Otherwise, with an address: match on
     `(merchant, normalized_address)`, or create.
   - Otherwise: `None`.
3. **Duplicate guard:** look up a receipt in the household by MARK, by
   (country, VAT, UID), or by `source_key`. If one exists, return
   `(existing, DUPLICATE)`. Otherwise create the receipt in a savepoint.
   An `IntegrityError` on an identity constraint (a concurrent
   import) means: re-fetch the existing receipt and return `DUPLICATE`.
4. **Receipt fields:**
   - `document_kind` from `canonical.document.kind`
   - `status = CANCELLED if cancellation_mark else ACTIVE`
   - `payment_method`: the one payment's method; several different
     methods → `MIXED`; none → `UNKNOWN`
   - `validation_warnings = [issue.to_dict() for issue in issues]`
   - `source_data = canonical.to_json()` without `source_url`
5. **Items:** built from `canonical.lines` (the canonical `unit` is
   already resolved by the provider):
   - `normalized_description = normalize_text(description)`
   - Classify (§13.1).
   - `bulk_create`.
6. **Matching:** `products.matching.match_items(receipt, items)`
   (§13.2). It sets the items' product and match status.
7. **Prices:** `products.prices.refresh_prices(items)` (§13.4).
8. Set `job.receipt` and `job.outcome = CREATED`.

Until M4 adds products, M3 stores `product` lines as `needs_review` and
skips steps 6 and 7. M4's `backfill_matching` command matches them.

**Receipt deletion** (`services/receipts.py: delete_receipt`), in a
transaction: set `outcome=RECEIPT_DELETED` on every job pointing at the
receipt, then `receipt.delete()`. This cascades to items. Products and
mappings are kept.

### 12.6 Maintenance tasks

| Task | Schedule | Behavior |
|---|---|---|
| `run_due_imports` | every 60 s | `process_import.delay(id)` for each `pending` job with `next_attempt_at <= now()` (batch 100). Covers scheduled retries, lost messages and crashed workers. An extra message is harmless: the claim ignores jobs that are not due |
| `flush_expired_tokens` | daily 03:20 | `call_command("flushexpiredtokens")` (exists since M1) |

### 12.7 Celery configuration (`config/celery.py`, settings)

```python
CELERY_BROKER_URL = f"{REDIS_URL}/0"
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 300}
CELERY_TASK_DEFAULT_QUEUE = "maintenance"
CELERY_TASK_ROUTES = {"receipts.*": {"queue": "imports"}}
CELERY_BEAT_SCHEDULE = {...}          # §12.6

@shared_task(name="receipts.process_import", soft_time_limit=60, time_limit=90,
             rate_limit=IMPORT_TASK_RATE_LIMIT)
def process_import_task(job_id: str) -> None:
    with log_context(job_id=job_id):
        pipeline.process_import(UUID(job_id))
```

A soft time limit (`SoftTimeLimitExceeded`) is handled as an internal
error: the job fails and can be retried manually. If a hard time limit
or a crash kills the worker, the transaction rolls back and the job is
due again when its lease ends. Each such attempt still counts, so a job
that crashes the worker every time ends up `failed` once the schedule is
used up.

## 13. Classification, matching, normalization (`apps/products`, `receipts/classification.py`)

### 13.1 Line classification

```python
DISCOUNT_KEYWORDS = ("ΕΚΠΤΩΣ", "ΚΟΥΠΟΝ", "DISCOUNT")
FEE_KEYWORDS = ("ΠΕΡΙΒΑΛΛΟΝΤΙΚ ΤΕΛ", "ΕΓΓΥΗΣ")      # carrier-bag fee, deposit
# No bare "ΣΑΚΟΥΛ": bags and garbage bags are products on real LIDL receipts.

def classify(line: Line, normalized_description: str) -> LineType:
    if line.gross < 0:
        return DISCOUNT if _has(normalized_description, DISCOUNT_KEYWORDS) else OTHER
    if _has(normalized_description, DISCOUNT_KEYWORDS): return DISCOUNT
    if _has(normalized_description, FEE_KEYWORDS):      return FEE
    if line.net == 0 and ((line.fees or 0) + (line.other_taxes or 0)) > 0: return FEE   # net known
    return PRODUCT
```

`_has()` compares `normalize_text()` keys: a keyword matches the start
of a word, and a two-word keyword matches two consecutive words
(`ΠΕΡΙΒΑΛΛΟΝΤΙΚ ΤΕΛ` matches `ΠΕΡΙΒΑΛΛΟΝΤΙΚΟ ΤΕΛΟΣ`).

The keyword lists are plain constants. A new keyword is a code change
with a test, which is fine at this scale.

### 13.2 Matching (`products/matching.py`)

```python
def match_items(items: list[ReceiptItem], *, merchant) -> None
def match_item(item: ReceiptItem, *, merchant) -> None   # sets product, match_status; no save
def rematch_receipt(receipt) -> int   # unlinked product lines only; admin action, backfill_matching
```

The pipeline builds the lines in memory, classifies and matches them,
sets their prices (`apply_prices`), and writes them with one
`bulk_create`.

**`match_item` for `line_type == product`:**

1. `key = ("code", code)` if `merchant_product_code` is set, otherwise
   `("desc", normalized_description)`.
2. `mapping = lookup(household, merchant, key)`.
   - Found, code key, and
     `SequenceMatcher(None, item.normalized_description, mapping.normalized_description).ratio()
     < settings.MATCH_GUARD_SIMILARITY` → `NEEDS_REVIEW`, no product. The
     merchant may have reused the code. The mapping is not touched.
     (`difflib` from the standard library: no database extension.)
   - Found otherwise → `MATCHED` to `mapping.product`, and the mapping
     remembers the line: `last_seen_description`, and for code mappings
     `normalized_description` too (it is the guard's reference).
   - Not found → `create_auto_product(item)` and a new mapping, inside a
     savepoint. An `IntegrityError` on the mapping's unique constraint
     (a concurrent import of the same new item) means: roll back the
     savepoint and use the existing mapping.

Lines that are not products get `NOT_A_PRODUCT` with no product.

**`create_auto_product(item)`:** `name = item.description`,
`normalized_name = item.normalized_description`, no category (spending
by category falls back to the merchant's default category at query
time), and a package size from `packages.suggest(description)` for
`piece` lines when it is unambiguous (§13.3).

### 13.3 Units and package parsing (`products/units.py`, `products/packages.py`)

```python
TO_BASE = {"g": ("kg", Decimal("0.001")), "kg": ("kg", Decimal(1)),
           "mg": ("kg", Decimal("0.000001")), "ml": ("l", Decimal("0.001")),
           "cl": ("l", Decimal("0.01")), "l": ("l", Decimal(1)), "piece": ("piece", Decimal(1))}

def to_base(quantity: Decimal, unit: str) -> tuple[Decimal, str]   # never converts mass ↔ volume

# Unit letters accept Latin and Greek look-alikes: KG|ΚΓ|KIL[OA], MG, G|GR|ΓΡ, ML, CL,
# L|LT|LTR|ΛΙΤ(ΡΟ|ΡΑ). A number may follow an abbreviation dot but not a decimal one.
SIZE_TOKEN = r"(?<![\d/])(?<!\d[.,])(\d+(?:\.\d+)?)\s?(<unit>)(?![A-ZΑ-Ω0-9])"
MULTIPACK  = r"\d\s?[XΧ×]\s?\d"            # 6X330ML, 5+1X330ML
SLASH_PACK = r"\d\s?/\s?\d+(?:\.\d+)?\s?(<unit>)"   # 27/250ML

def suggest(description: str) -> PackageSuggestion | None:
    """Works on the uppercased, accent-free description with decimal commas as dots
    (not normalize_text: it would drop the '/' of slash packs).
    Returns None if MULTIPACK or SLASH_PACK matches, or if there is not exactly one SIZE_TOKEN.
    Percentages are removed before matching ('1,5%' never becomes a size). mg → g."""
```

Unit tests cover every row of the requirements §9.4 table, the edge
cases (`500GR`, `1,5LT`, `2 X 1L`, `ΓΑΛΑ 3,5% 1L`) and real LIDL lines
(`MSC ΦΙ.ΤΟ.ΦΥ.Ζ.195G`, `XAΡ.ΚΟΥΖ.2ΠΛΑ ΦΥΛ1ΚG`, `CO.COLA ZE.5+1X330ML`).

### 13.4 Normalized prices (`products/prices.py`)

```python
def apply_prices(item) -> None:      # in memory, from item.product (the pipeline, before bulk_create)
def refresh_prices(items: Iterable[ReceiptItem]) -> None:
    """apply_prices on each item (select_related product), then bulk_update them."""

def normalize(item, product) -> tuple[Decimal | None, str | None, Decimal | None]:
    if item.line_type != PRODUCT or product is None or item.quantity is None:
        return None, None, None
    if item.unit in (KG, L):                     q, u = to_base(item.quantity, item.unit)
    elif item.unit == PIECE and product.package_quantity:
                                                 pq, u = to_base(product.package_quantity, product.package_unit)
                                                 q = item.quantity * pq
    elif item.unit == PIECE:                     q, u = item.quantity, "piece"
    else:                                        q, u = item.quantity, "other"
    price = (item.gross_amount / q) if q else None     # full precision, then ROUND_HALF_UP
    return q (6 dp), u, price (4 dp)                   # to the column scales

PRICE_HISTORY = Q(line_type=PRODUCT, product__isnull=False, normalized_unit_price__isnull=False,
                  quantity__gt=0, gross_amount__gt=0,
                  receipt__status=ACTIVE, receipt__document_kind=SALE)
```

Triggers: pipeline persist, `match`, `create-product`, reclassification,
product merge, product package change (all items of the product), and
the admin "recompute prices" action. Receipt status is a query filter
(`PRICE_HISTORY`), so cancellation needs no resync.

### 13.5 Review services (`products/review.py`)

Each service runs in a transaction and refreshes the affected items'
prices:

- `link_item(item, product)`: sets `product` and `MATCHED`, and upserts
  the mapping on the item's key to point at `product`. If the previous
  product is left with no items and no mappings, it is deleted.
- `create_product_for_item(item, **values)`: creates a product, then
  calls `link_item`. Both raise `LineNotProduct` (`409
  not_a_product_line`) for non-product lines.
- `update_item(item, line_type=, user_note=)`: a non-product type sets
  `NOT_A_PRODUCT` and clears the product. Setting it back to `product`
  runs `match_item` again.
- `update_product(product, **changes)`: a package size change refreshes
  the prices of all its lines (also from the product admin).
- `merge_products(target, sources)`:
  1. Lock all the products (`select_for_update`, ordered by id) and
     validate: same household, the target not among the sources.
  2. Repoint the sources' mappings to the target. Mapping keys are
     unique per household and merchant whatever the product, so they
     never collide.
  3. Point the source items at the target and `refresh_prices` them.
  4. Delete the sources.

Price history queries live in `products/history.py`: `price_entries()`
(the `PRICE_HISTORY` lines of a product, filtered and newest first),
`price_stats()` (per normalized unit and currency) and `compare()`
(one unit and currency group, ranked only when comparable).

## 14. API surface

All routes are under `/api/v1/` (`config/api_urls.py`). Each app
exposes a `urls.py` with named routes. **HS** = household-scoped through
`HouseholdScopedMixin`.

| Method and path | View | Auth | Notes |
|---|---|---|---|
| `POST auth/register` | `RegisterView` | none | throttle `register` (10/hour/IP) |
| `POST auth/login` | `LoginView` (simplejwt) | none | `LoginRateThrottle` |
| `POST auth/refresh` | `TokenRefreshView` | none | rotation |
| `POST auth/logout` | `LogoutView` | user | blacklists |
| `GET auth/me` | `MeView` | user | memberships included |
| `POST auth/password/change` | `PasswordChangeView` | user | revokes refresh tokens |
| `GET households` | `HouseholdViewSet.list` | user | the user's households |
| `GET/PATCH households/{id}` | `HouseholdViewSet` | member / owner | non-member → 404 |
| `GET households/{id}/members` | `MemberViewSet` | member | |
| `DELETE households/{id}/members/{mid}` | `MemberViewSet` | owner or self | `409 last_owner` |
| `GET/POST households/{id}/invitations` | `InvitationViewSet` | owner | the code only in the POST response |
| `DELETE households/{id}/invitations/{iid}` | `InvitationViewSet` | owner | sets `revoked_at` |
| `POST households/join` | `JoinView` | user | |
| `POST receipts/import` | `ReceiptImportView` | HS | throttles `import_minute` and `import_day`. Body at most 4 KB (`SmallJSONParser`). Response: `ImportSubmitResponseSerializer` (the import plus `duplicate`) |
| `GET receipt-imports` | `ImportJobViewSet` | HS | filter `status`, `created_from`, `created_to` |
| `GET receipt-imports/{id}` | `ImportJobViewSet` | HS | |
| `POST receipt-imports/{id}/retry` | `ImportJobViewSet.retry` | HS | `202` with the import. `409 not_retryable` unless `failed`. Resets `attempt_count` |
| `GET receipts` | `ReceiptViewSet` | HS | `ReceiptFilter`, ordering |
| `GET/PATCH/DELETE receipts/{id}` | `ReceiptViewSet` | HS | PATCH whitelist (§12.5) |
| `GET receipt-items/review` | `products.api.ReceiptItemViewSet.review` | HS | `needs_review` lines, paginated |
| `PATCH receipt-items/{id}` | `ReceiptItemViewSet` | HS | `line_type`, `user_note` |
| `POST receipt-items/{id}/match` | `ReceiptItemViewSet.match` | HS | `200` with the line. `409 not_a_product_line` for non-product lines |
| `POST receipt-items/{id}/create-product` | `ReceiptItemViewSet.create_product` | HS | `201` with the line |
| `GET/POST products` | `ProductViewSet` | HS | `ProductFilter`, substring `q` |
| `GET/PATCH products/{id}` | `ProductViewSet` | HS | a package change refreshes prices |
| `GET products/{id}/prices` | `ProductViewSet.prices` | HS | paginated price-history lines + `stats` |
| `GET products/{id}/price-comparison` | `ProductViewSet.price_comparison` | HS | `products.history.compare` |
| `POST products/{id}/merge` | `ProductViewSet.merge` | HS | `200` with the target |
| `GET merchants`, `GET merchants/{id}` | `merchants.api.MerchantViewSet` | HS (via receipts) | `scope_queryset`: `annotate(receipt_count=Count("receipts", filter=Q(receipts__household=h)), last_receipt_at=Max(...)).filter(receipt_count__gt=0)`: one grouped query, no duplicates |
| `GET stores` | `merchants.api.StoreViewSet` | HS (via receipts) | `?merchant=`, scoped like merchants |
| `GET/POST categories`, `GET/PATCH/DELETE categories/{id}` | `products.api.CategoryViewSet` | HS (own + system) | Not paginated. System rows `403 system_category`. DELETE `409 category_in_use` while products use it |
| `GET analytics/*` | `analytics.api` views | HS | §15 |
| `GET /healthz`, `GET /readyz` | `common.health` | none | outside `/api/v1` |
| `GET /api/schema/`, `/api/docs/` | drf-spectacular | none in dev; staff in prod | |

**Serializers**

- Every model has explicit `fields` lists. Nothing uses `__all__`.
- Read and write serializers are separate where they differ.
- `ReceiptDetailSerializer` nests the merchant, store, items (with a
  `ProductSummary`) and warnings, using `select_related` and
  `prefetch_related("items__product__category")`.
- `ImportJobSerializer` exposes `source_host` and `issuer_vat`, never
  `submitted_url`. `next_attempt_at` is shown only while a retry is
  scheduled (the claim lease stays internal).
- `ReceiptDetailSerializer` reads `coverage`, `vat_breakdown` and
  `payments` from `source_data`. Until M4 it has no product summaries.
- Money: `DecimalField` serializes as a string, paired with a
  `currency` field.

**Filters (django-filter)**

- `ReceiptFilter`:
  - `issued_from` / `issued_to` (dates turned into household-tz bounds)
  - `merchant`, `store`
  - `min_total` / `max_total` on `gross_total`
  - `product` and `category`: `items__product` / `items__product__category`,
    with `distinct()`
  - `needs_review` (an `Exists` on `needs_review` items),
    `has_warnings` (`validation_warnings` not empty), `status`,
    `document_kind`
  - `q`: `merchant__display_name__icontains` OR
    `items__normalized_description__contains=normalize_text(q)`
- `ProductFilter`: `q` (`normalized_name__contains=normalize_text(q)`),
  `category`, `brand`, `merchant` (via mappings).

**OpenAPI:** tags per app, `@extend_schema` on custom actions, enum
naming overrides for clashing choice names, and documented error codes.

## 15. Analytics implementation (`apps/analytics`)

```python
# periods.py (pure Python)
@dataclass(frozen=True)
class Period:
    first: date; last: date                     # inclusive days
    def previous(self) -> Period                # same length, immediately before
    def bounds(self, tz) -> tuple[datetime, datetime]   # local midnights, [start, end)

# queries.py
def included_receipts(household, period) -> QuerySet[Receipt]:
    start, end = period.bounds(ZoneInfo(household.timezone))
    return Receipt.objects.filter(household=household, status=ACTIVE, excluded_from_analytics=False,
                                  currency=household.default_currency,
                                  issued_at__gte=start, issued_at__lt=end)

SIGNED_GROSS = Case(When(document_kind=CREDIT_NOTE, then=-F("gross_total")), default=F("gross_total"))
```

The summary aggregates over all the household's active receipts in the
period with `filter=Q(currency=…)` on each aggregate, so the same query
also counts `other_currency_receipts`.

| Endpoint | Query sketch |
|---|---|
| `summary` | `aggregate(total=Sum(SIGNED_GROSS), sales_count=Count("id", filter=Q(document_kind=SALE)), sales_sum=Sum("gross_total", filter=Q(document_kind=SALE)), credit_total=Sum("gross_total", filter=Q(document_kind=CREDIT_NOTE)))`. The previous period runs the same query. `needs_review_count` counts the household's `ReceiptItem` rows with `match_status=needs_review` |
| `spending-by-merchant` | `values("merchant_id", "merchant__display_name").annotate(total=Sum(SIGNED_GROSS), receipts=Count("id")).order_by("-total")` |
| `spending-by-category` | On `ReceiptItem` joined to the included receipts: annotate a `bucket` with `Case`: product line → `Coalesce(product__category_id, receipt__merchant__default_category_id)`, else `'uncategorized'`; `discount` → `'discounts'`; `fee` → `'fees_deposits'`; `other` → `'other_adjustments'`. Then `values("bucket").annotate(total=Sum(signed line gross))`. The **remainder** per receipt (Σ signed receipt gross − Σ signed line gross, which is the whole amount for summary-only receipts) goes to the merchant's default category or `'unallocated'`: one more grouped query on receipts by `merchant__default_category_id`, then subtracting the line sums per category in Python. Category names are resolved in one query |
| `monthly-trend` | `annotate(month=TruncMonth("issued_at", tzinfo=tz)).values("month").annotate(total=Sum(SIGNED_GROSS), receipts=Count("id"))`. Missing months filled with 0 in Python |
| `top-products` | `ReceiptItem` filtered by `PRICE_HISTORY` (§13.4), the household and the included receipts: `values("product_id", "product__name").annotate(receipts=Count("receipt_id", distinct=True), spend=Sum("gross_amount"), quantity=Sum("normalized_quantity"))`, ordered by `by` |
| `products/{id}/prices` | `products.history.price_entries()`: the product's `PRICE_HISTORY` rows (merged sources included through repointing), filtered, newest first, paginated. `stats` per `normalized_unit` and currency, computed in Python over all matching rows (a household buys one product a few hundred times at most): latest, previous, min, max, count, `Σ gross ÷ Σ normalized quantity` |
| `products/{id}/price-comparison` | `products.history.compare()`: the same rows in one (`normalized_unit`, currency) group (the requested unit, else the largest group), statistics per merchant, ranked by average when at least 2 merchants and the unit is not `other`; otherwise `comparable=false` with `no_prices`, `one_merchant` or `unknown_unit` |

All analytics endpoints default to the current month in the household
timezone. Query count stays constant (no N+1) and is asserted in tests.

## 16. Observability (`common/logging.py`)

- **`RequestContextMiddleware`:** reads `X-Request-ID` (when valid) or
  generates a UUID4 and echoes it in the response. It binds
  `request_id`, `user_id` and `household_id` into `contextvars`.
- **Celery:** `task_prerun` / `task_postrun` signal handlers bind and
  clear `task_id` and `job_id`.
- **`ContextFilter`** adds those fields to every log record.
  **`RedactFilter`** replaces any `https?://\S+` in the message and its
  args with `<url>`, as a safety net. It also formats and redacts
  tracebacks into `exc_text`, because an exception message can quote a
  URL. `exc_info` stays on the record for Sentry, which reads records
  after the handlers and scrubs its own events. Services log `url_fp`
  (12 hex characters) and `host`. The pipeline binds `provider` too.
- **Error handlers:** `handler400`, `handler404` and `handler500` answer
  with the error envelope, so a Django-level 400 (a body over 16 KB)
  is JSON too.
- **Formatters:** `apps.common.logging.JsonFormatter` (prod), a
  python-json-logger subclass that redacts the tracebacks it formats
  itself, or a console formatter (dev). Gunicorn's access log is disabled, because
  Django logs requests with status, duration and path.
- **Sentry** (`apps/common/sentry.py`, initialized by `prod.py` when
  `SENTRY_DSN` is set): `DjangoIntegration` and `CeleryIntegration`.
  - **Not sent:** local variables (`include_local_variables=False`) and
    request bodies (`max_request_body_size="never"`). `send_default_pii`
    keeps its default (off); the option is deprecated in sentry-sdk 2.x.
  - **`before_send`:**
    - drops the request data, query string, cookies and the
      `Authorization`, `Cookie`, `Referer` and forwarding headers
    - replaces every URL-shaped string elsewhere with `<url>`, keeping
      the request URL (our own API path)
    - tags the event with `request_id`, `task_id`, `job_id`,
      `household_id` and `provider` from the log context
  - **`before_breadcrumb`** redacts URLs the same way.
  - Unexpected import errors are always `internal_error`, so there is no
    `error_code` tag.
- **`/readyz`:** `SELECT 1` and a Redis `PING`, each with a short
  timeout. Returns `200 {"status": "ok"}` or `503 {"status":
  "unavailable"}`.
- **No stats endpoint** (D21). Import health is read in the admin: the
  import job list filters on status, provider and error code, and
  receipts filter on `parser_version`. Unsupported hosts and unknown
  fields are log lines (`host`, `provider`, label), never URLs.
- **Admin:** list filters and search on every model. Actions: retry
  import, re-run matching for selected receipts, recompute prices.

## 17. Security controls (requirement → implementation)

| Requirement | Implementation |
|---|---|
| No generic fetch | `SafeFetcher` is only constructed inside `pipeline`. Providers receive it as an argument, and nothing else imports it (checked by the dependency-rule test) |
| SSRF (§15.1) | §10. Tests for each rule |
| Household isolation | `HouseholdScopedMixin`, service signatures, the isolation-matrix test (§18.4) |
| Enumeration | UUID ids, 404 for foreign objects, the same 403 for unknown and foreign households |
| Personal data | Allowlist in the parser plus an explicit drop list. The Impact payload keeps only known fields (no free-text miscellaneous section). `source_data` stores unknown fields by name only, never their values, and drops Luhn-valid card-number runs from payment labels. A test asserts the sanitized fixture's personal markers are absent from `source_data` and from the database after import |
| URL secrecy | Not in the job serializer. Log redaction. Sentry scrubbing (§16). `tests/receipts/test_url_secrecy.py` captures the real log handler's output during imports from every provider, failures and rejected links, and asserts no receipt URL or URL token appears |
| Secrets | Environment only. `prod.py` refuses to start with a default or missing `DJANGO_SECRET_KEY` |
| Passwords | Argon2. Django validators. API login throttles. Admin login throttle (`throttle_admin_login`, 429 per IP) |
| Tokens | 15-minute access tokens. Rotating, blacklisted refresh tokens. Revoked on password change |
| Abuse | DRF throttles (retries count against the import limits). 16 KB body limit, enforced by `LimitedJSONParser` (DRF reads the stream directly, so Django's `DATA_UPLOAD_MAX_MEMORY_SIZE` alone does not apply). 1 MB cap at the proxy. URL length limit. Import task rate limit. `NUM_PROXIES=1` in prod, so throttles use the address Caddy saw |
| Transport | Caddy HTTPS with a local CA (LAN and VPN only, no public exposure). HSTS. Secure cookies (admin) |
| Containers | Non-root user, slim base image, no build tools in the prod image, `.dockerignore` excludes `.env` and fixtures from the prod image context where possible |

## 18. Testing

### 18.1 Layout and tooling

```text
backend/tests/
├── conftest.py               # api_client, user, household, member_client, other_household …
├── factories.py              # factory-boy factories for every model
├── fixtures/impact/
│   ├── sample_el.html        # sanitized real receipt (Greek culture)
│   ├── sample_en.html        # same receipt, English culture
│   ├── not_found.html
│   └── expected/*.json       # golden canonical JSON per real fixture
├── receipts/impact.py        # fixture loading + variant-building helpers (add_line, set_tax, …)
├── common/ accounts/ households/ merchants/ receipts/ products/ analytics/
└── test_architecture.py      # dependency rules (§2.2)
```

- `pytest -p no:cacheprovider --ds=config.settings.test`, run inside
  Docker against the `db` service. pytest-django creates
  `test_<db>` automatically.
- Markers: `live` (skipped unless `RUN_LIVE_TESTS=1`) and `slow`.
- Time-dependent tests set timestamps relative to `timezone.now()` (or fixed factory dates) instead of freezing the clock.
- `django_assert_max_num_queries` for N+1 guards.

### 18.2 Fixtures

- **Real pages, per provider:**
  - Layout: `tests/fixtures/<provider>/<name>.html`, passed through
    `sanitize_fixture`, with `<name>.meta.json` holding the sanitized
    URL, a description and the expectation (warning codes, or an error
    code).
  - The harness `tests/receipts/test_fixtures.py` discovers every meta
    file, parses the page through the registry and compares the result
    with `expected/<name>.json`.
  - Golden files are regenerated with `pytest --update-golden`, and
    every change is reviewed in the diff.
  - Current fixtures:
    - Impact: sample (Greek and English cultures), not found.
    - Entersoft: 2 LIDL receipts, shell, not found.
    - AADE: cash-register receipt, signature mismatch, not
      transmitted.
- **Synthetic variants** are generated in code from the sanitized
  sample (`tests/receipts/impact.py`), not stored as HTML files.
  `add_line()` adds a line to both views and updates every total, so
  variants stay internally consistent. Each variant changes one thing:
  - `discount_line`: a negative line with a discount description.
  - `bag_fee`: a carrier-bag line with a fee amount.
  - `multi_vat`: 6%, 13% and 24% lines with a matching VAT breakdown.
  - `credit_note`: type 11.4.
  - `cancelled`: non-zero cancellation MARK.
  - `cash`: payment code 3.
  - `no_mark_transmission_failure`.
  - `missing_optional`: no branch block, no tax office.
  - `missing_required`: no gross total, so `FormatChanged`.
  - `views_disagree`: one line's gross differs, so
    `InconsistentSource`.
  - `uid_mismatch`.
  - `unknown_layout`: invoice container renamed.
  - `bad_number`: `1.234,5,6`.
- **New real receipts:** when you add them, run them through
  `sanitize_fixture`, add a meta file and a golden file, and promote them over
  the synthetic variants they replace.

### 18.3 Test suites by milestone

| Suite | Highlights |
|---|---|
| `common` | `parse_decimal` table tests (both cultures, rejects), datetime parsing incl. DST edges, `normalize_text` (tonos, final sigma, look-alike letters), error envelope shapes, household resolution matrix |
| `accounts` / `households` | register (invite, open, closed), login throttle, refresh rotation and blacklist, password change revokes, invitations (expired, revoked, reused), last-owner rules |
| `receipts.providers` | golden fixtures, page classification, culture detection, cross-check failures, the personal-data absence assertion, URL recognition and canonicalization table |
| `receipts.fetching` | fake resolver → private, loopback, link-local, CGNAT, `::1`, `fc00::/7`, IPv4-mapped → blocked. Mixed answer → blocked. Pool called with the pinned IP and `server_hostname`. 3xx → `FormatChanged`. 404 → `NotFound`. 503 → transient. Size cap (plain and gzip bomb). Deadline. Content type |
| `receipts.validation` | one test per rule R4–R12, tolerance boundaries |
| `receipts.pipeline` | happy path, every error-to-job mapping, the retry schedule and `run_due_imports`, the lease (a second claim of a just-claimed job does nothing; an expired lease is claimed again; attempts exhausted by crashes → `failed`), rollback on an exception injected after items are created (no rows left), duplicate by MARK from a different URL, delete and reimport |
| `receipts.api` | all requirements §6.2 cases, concurrent submits (`transaction=True`, two threads → one job), retry endpoint, throttles |
| `products` | `suggest()` table, `to_base`, every matching branch incl. the guard, the concurrent new-item race (two imports → one product), link (next import matches), merge (moves, mapping conflicts, sources deleted, prices refreshed), `refresh_prices` on every trigger, each normalization case |
| `analytics` | bucket-sum invariant (randomized receipts), merchant-category fallback, credit and cancelled handling, month boundary at 23:30 Athens on the last day of a month, previous-period math, query counts |

### 18.4 Isolation matrix

`tests/test_isolation.py`:

1. Collects every URL pattern under the `api-v1` namespace.
2. Each route name must appear either in `ISOLATION_CASES` (a dict of
   route → a factory that creates an object in household B, plus the
   methods to try) or in `NOT_HOUSEHOLD_SCOPED` (auth, health, schema).
   **An unlisted route fails the test,** so a new endpoint cannot skip
   isolation.
3. For each case, the household-A client calls the route with B's
   object. Expect 404 on detail and actions, and B's data absent from
   lists. With `X-Household-ID: B`, expect 403.

### 18.5 End-to-end acceptance

`tests/receipts/test_e2e_import.py` implements §18 steps 1–7 of the
requirements, with `SafeFetcher` replaced by a stub that returns
`sample_el.html`. It uses `django_capture_on_commit_callbacks(execute=True)`
so the enqueue runs, and the task function runs synchronously.

### 18.6 Coverage and checks

- `make check` fails if overall coverage is below 85%.
- A coverage report per package is printed. The target is at least 90%
  for `receipts.providers`, `receipts.services`, `receipts.validation`
  and `products.matching`. This is reviewed per milestone; it is not
  enforced at first.

## 19. Milestone mapping

| Milestone | Sections of this document |
|---|---|
| M1 Foundation | §3, §4, §5, §6, §7, §16 (`healthz`, `readyz`, request context), §18.1, §18.4 harness |
| M2 Provider (no DB) | §9, §10, §11, §6.4, `parse_receipt` and `sanitize_fixture` commands, §18.2; M2b: §9.7 |
| M3 Pipeline | §8.1, §8.2, §12, §13.1, the receipts part of §14, admin |
| M4 Products | §8.3, §13.2–§13.5, the products and review part of §14 |
| M5 Query and analytics | §14 filters, §15, merchants, stores and categories endpoints, performance |
| M6 Operations | §16 (Sentry, admin filters), §17, `compose.prod.yaml`, backup and restore, deployment docs |

## 20. Technical risks and mitigations

| Risk | Mitigation |
|---|---|
| Impact changes its HTML | Two-view cross-check, required-field checks, unknown-field logging, golden fixtures, `make parse-receipt` against the live link, a parser version on every receipt (re-parse with `retry`) |
| Unknown codes on future receipts | Raw codes kept in `source_data`, a log line per unknown code. Add codes when samples appear |
| Package-size suggestions are wrong | Applied only when unambiguous. Users can correct them, and prices are recomputed |
| Merchant item codes reused for another product | Similarity guard → `needs_review` |
| Redis loss or restart | No data in Redis. `run_due_imports` rebuilds the queue from PostgreSQL |
| Duplicate imports under concurrency | Database unique constraints and savepoints (receipts, jobs and mappings) |
| Trimmed features turn out to be needed (D21) | Each was removed before implementation and can be added in isolation: a purge task, a snapshot table, fuzzy suggestions with `pg_trgm`, a stats view |
| Celery ETA redelivery with Redis | No ETAs. Retries are scheduled in the database |
| Only one real fixture | Synthetic variants, plus a repeatable sanitize-and-golden workflow for new receipts |
