# Eksoda: household expense and receipt backend

This is a Django/DRF backend. It imports Greek e-receipts from the URLs in
their QR codes, then builds product price history and household spending
analytics. An Android scanner app and a web frontend will be built later
against this API.

## Read before changing anything

| Doc | Use it for |
|---|---|
| `docs/requirements.md` | *What* to build. Cited as `§x.y` |
| `docs/technical-design.md` | *How* to build it. Cited as `TD §x.y` |
| `docs/implementation-plan.md` | Milestone order, tasks, exit criteria and current status |
| `docs/providers/impact.md` | The real Impact receipt page format |
| `docs/requirements-review.md` | Why the requirements look the way they do |
| `docs/android-app.md` | How the Android client uses this API, and the API gaps it found (§15) |
| `docs/deployment.md` | Production stack, Raspberry Pi notes, backup/restore, runbook |

## Ground rules

- **Everything runs in Docker.** Never install or run Python, uv,
  PostgreSQL or Redis on the host. Use the `make` targets, which wrap
  `docker compose`.
- **Never run `git init`, commit or push** unless the owner asks. The
  owner manages git.
- **Follow the milestones in order.** Do not build features from a
  later milestone early. Record any deviation from the docs in the docs
  themselves.
- **Money and quantities are `Decimal`.** Never use `float`. Use the
  field factories in `apps/common/fields.py` (added in M3).
- **Receipt URLs work like passwords.** Never log them or return them
  in import/job responses. Log the host and a fingerprint instead.
- **Personal data from receipts is never stored.** That covers loyalty
  or customer codes, card transaction IDs, POS terminal IDs and
  signatures.
- **Household isolation:**
  - Every household-scoped view uses `HouseholdScopedMixin`
    (`apps/common/households.py`).
  - Another household's objects return 404.
  - Every new API route must be registered in `tests/test_isolation.py`,
    or the test fails.
- **Provider code is pure Python.** `apps/receipts/providers/**` must
  not import Django (checked by `tests/test_architecture.py`).
- **Receipt sources:** `impact`, `entersoft` and `aade_fhm`
  (`docs/providers/`). New formats are expected: add them as a new
  provider or a new layout (`add-provider` skill), extend
  `apps/receipts/vocabulary.py` for new labels, and never special-case
  a source outside `apps/receipts/providers/`.
- **No live network in tests,** except tests marked `@pytest.mark.live`.

## Commands (run from the repo root)

```bash
make up                      # dev stack: db, redis, migrate, api (:8000), worker, beat
make down
make logs
make test ARGS="tests/accounts -k login"
make check                   # ruff, format check, makemigrations --check, pytest + coverage
make makemigrations
make migrate
make lock                    # after changing dependencies in backend/pyproject.toml
make shell
make bootstrap EMAIL=you@example.com HOUSEHOLD="Home"
make parse-receipt SRC=<url | backend-relative path> [ARGS=--json]   # no database
make manage ARGS="backfill_matching"                                  # match lines that have no product
make manage ARGS="seed_demo_data --household <id>"                   # demo receipts (development)
make sanitize-fixture PROVIDER=<code> IN=/abs/raw.html OUT=tests/fixtures/<code>/x.html
make test-live URLS="<url> <url>"                                     # opt-in, real network
make test ARGS="tests/receipts/test_fixtures.py --update-golden"      # rewrite golden files, then review the diff
make prod-up                 # production stack (compose.prod.yaml); any target takes PROD=1
make prod-ca                 # export the proxy's local root CA (LAN/VPN only, no public certificate)
make backup                  # pg_dump into backups/; make restore FILE=… CONFIRM=yes
```

`make check` must pass before any task counts as done.

- Swagger UI: http://localhost:8000/api/docs/
- Admin: http://localhost:8000/admin/

## Code conventions

- **Layout:** `backend/config/` holds settings (`base`, `dev`, `test`,
  `prod`) and URLs. Each app has `models.py`, `services.py`, `admin.py`
  and `api/{serializers,views,urls}.py`. `receipts` has a `services/`
  package instead (`imports`, `pipeline`, `persistence`, `receipts`).
  `backend/tests/` mirrors `apps/`.
- **Business logic lives in `services.py`.** Service functions take an
  explicit `household` or `user` argument. Views stay thin.
- **Errors:**
  - Raise `ApiError` subclasses with a stable `default_code`.
  - The response envelope is
    `{"error": {"code", "message", "details"}}`.
  - Document every new code.
- **API conventions:**
  - Paths live under `/api/v1/`, with no trailing slash.
  - Route names live in the `api-v1` namespace.
  - Serializers list their `fields` explicitly; never use `__all__`.
- **Tests:** pytest with factories in `tests/factories.py`. The coverage
  floor is 85% (enforced in `make check`).
- **Style:** American English in code, comments and docs. Formatting
  is handled by ruff (line length 100).

## Project skills (`.claude/skills/`)

| Skill | Use when |
|---|---|
| `api-endpoint` | Adding or changing an API endpoint |
| `model-change` | Adding or changing models and migrations |
| `receipt-fixture` | Adding a new real receipt from a supported source as a sanitized fixture |
| `add-provider` | A receipt link from an unsupported host, or a provider that changed its page format |
| `milestone-check` | Verifying a milestone against its exit criteria and updating the docs |
