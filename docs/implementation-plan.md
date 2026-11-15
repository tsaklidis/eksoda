# Implementation plan: server MVP

**Based on:** `docs/requirements.md`
**Date:** 2026-11-13

Each milestone leaves the application runnable and tested, and is
reviewed before the next one starts. Section references (§) point to
`docs/requirements.md`. "TD §" points to `docs/technical-design.md`.

**Implementation does not start until the project owner has reviewed
the requirements.**

## 0. Repository assessment

- The repository contains only `docs/` and IDE settings
  (`.idea/`). There is no code yet.
- **Git is initialized manually by the project owner.** The
  implementation never runs `git init`. It only adds `.gitignore` and
  `.dockerignore`.
- The Android app will be built later and will adopt this server's API.
  The OpenAPI schema is the contract (D17).
- **Everything is dockerized** (D16). The host needs only Docker. Python,
  `uv`, PostgreSQL and Redis all run in containers.

## 1. Target layout

The full layout and module responsibilities are in TD §2. In short:

```text
eksoda/
├── compose.yaml  compose.override.yaml  compose.prod.yaml
├── .env.example  .gitignore  Makefile  README.md
├── docs/         # requirements, review, technical design, plan, providers/
├── ops/          # Caddyfile, backup.sh
└── backend/      # Dockerfile, pyproject.toml, uv.lock, config/, apps/, tests/
```

## 2. Milestones

Size is relative: S = under a day, M = 1–3 days, L = 3–5 days of
focused work.

### M1: Project foundation (M)

**Tasks**

1. Add `.gitignore` (including `.idea/`, `.env`, `backups/`),
   `.dockerignore` and `.env.example` (TD §3.4). Add `pyproject.toml`
   with ruff, pytest, pytest-django and coverage config. Generate
   `uv.lock` inside a container (`make lock`). Do **not** run
   `git init`.
2. Multi-stage `backend/Dockerfile` with `dev` and `prod` targets
   (TD §3.1). Add `compose.yaml` and `compose.override.yaml` with `db`
   (Postgres 17), `redis`, `migrate`, `api` (runserver in dev), and
   placeholders for `worker` and `beat` (TD §3.2). Add the Makefile, with
   every target running in containers (TD §3.3).
3. Create the Django 5.2 project with split settings via
   django-environ: UTC storage, `TIME_ZONE=Europe/Athens`, the Argon2
   hasher, WhiteNoise, and the Redis cache (TD §4).
4. `common` app: UUID/timestamp base model, error envelope exception
   handler, pagination class, `X-Household-ID` resolution, the
   `HouseholdScopedMixin` scoping mixin, and `/healthz` and `/readyz`.
5. `accounts`: a custom `User` (email login, case-insensitive unique)
   and simplejwt with rotation and blacklist. Endpoints `register`
   (invite-gated, D2), `login`, `refresh`, `logout`, `me` and
   `password/change`, with login throttling.
6. `households`: `Household`, `HouseholdMember`, `HouseholdInvitation`,
   their endpoints (§12.3) and the `bootstrap_household` command.
7. drf-spectacular schema and Swagger UI (sidecar assets, no CDN).
8. Request-context logging middleware (TD §16) and the dependency-rule
   test (TD §2.2).
9. README: setup with Docker only, bootstrap, tests, Makefile targets.

**Tests:** registration with and without an invite, login, refresh
rotation, logout blacklist, `me`, household header resolution (none,
single, multiple, foreign → 403), invitation lifecycle, last-owner
protection, and the first version of the isolation-matrix harness.

**Exit:** on a host with only Docker, `make up` runs the stack and
`make check` passes (ruff, format, `makemigrations --check`, tests). You
can authenticate through Swagger.

### M2: Provider integration with no persistence (L)

**Receipt samples:** M2 starts with the one real sample plus synthetic
variants (TD §18.2). More real receipts will be added as they become
available, ideally covering the unknowns in
`docs/providers/impact.md` §7. Each new receipt goes through
`sanitize_impact_fixture`, gets a golden file, and replaces the
synthetic variant it covers. The parser stays at version `impact/1`
until real samples confirm the discount, fee and credit-note handling.

**Tasks**

1. `canonical.py`: frozen dataclasses (§7.2).
2. `common` utilities: strict culture-aware decimal parsing, Greek and
   English datetime parsing to Europe/Athens, and text normalization
   (§9.5).
3. `fetching.py`: the SSRF-safe fetcher (§15.1), using urllib3 with a
   pinned IP, SNI and certificate checks, no redirects, timeouts, size
   and decompression caps, and fixed headers.
4. Provider protocol, registry and URL recognition, plus the
   `UrlIdentity` extraction for Impact.
5. Impact parser: page classification, commercial and tax view
   extraction, cross-check, required-field checks, the personal-data
   allowlist, and `unknown_fields`.
6. `mydata.py`: myDATA code maps (document types, VAT categories,
   measurement units, payment methods) with a raw fallback for unknown
   codes. Check them against the official AADE documentation (TD §9.2).
7. `validation.py`: rules R4–R12 (§10.2). R1–R3 live in the parser.
8. `sanitize_impact_fixture` command (TD §9.6). Fixtures: the sanitized
   sample (Greek and English culture), synthetic variants (TD §18.2),
   the not-found and unknown pages, and golden JSON files.
9. `manage.py parse_receipt <url|file> [--json]` for manual inspection.
   The live mode uses the safe fetcher.
10. Check Impact's terms of use for automated retrieval and note the
    result in `docs/providers/impact.md`.

**Tests:** parser fixture suite, fetcher security suite, validation
rules, decimal and date parsing, text normalization. One opt-in live
test.

**Exit:** `parse_receipt` turns the sample into the expected canonical
JSON (5 lines, 8.10 / 1.05 / 9.15, MARK, branch 264) without touching
the database. Coverage of at least 90% on the provider and validation
modules.

### M2b: Entersoft and AADE cash-register receipts (M), done

**Needs approval** of D19 and D20 (`requirements.md` §4). Formats are
documented in `docs/providers/entersoft.md` and
`docs/providers/aade.md`. The recommendation is to do this **before
M3**: the canonical model then meets three real sources before the
database schema freezes it.

**Tasks**

1. **Canonical and validation changes:**
   - `lines` may be empty for summary-only sources, with a
     `has_line_items` flag.
   - `Document.issued_at_precision` (`exact` or `date_only`) for sources
     without a time of issue.
   - R7 compares only components that every line provides.
   - New rules for sources with line discounts:
     qty × unit price = value before discount, and value before
     discount − discount = line total.
2. **Shared code maps:** document type label → myDATA code
   (`Απόδειξη Λιανικής Πώλησης` → `11.1`, …); VAT rate → category code;
   unit label → unit (`TEMAXIO`/`ΤΕΜΑΧ` → piece, `ΚΙΛΑ` → kg); payment
   label → method (`POS / e-POS` → card).
3. **Entersoft adapter:**
   - URL recognition (`entersoft:{doc uuid}` identity).
   - Two-step fetch (shell page, then the iframe document on the same
     host, both through the safe fetcher).
   - Parser: header, items table by column header, totals, VAT
     breakdown, payments, UID/MARK.
   - Arithmetic checks instead of a second view.
   - Personal blocks never read.
   - Sanitizer.
   - Fixtures from both real receipts with golden files.
4. **AADE cash-register adapter:**
   - URL recognition (`fhm:{register id}:{sequence}` identity).
   - Label/value parser with decimal-point numbers.
   - Cash-register VAT categories → rates, checked arithmetically.
   - Card/cash split.
   - Buyer VAT never read.
   - Sanitizer.
   - Fixture and golden file.
5. Registry entries for the two new hosts, an extended
   `parse_receipt` command, and live tests per provider (opt-in).

**Exit:** all three real sources (Impact, Entersoft ×2,
cash register ×1) parse through `make parse-receipt` with no
validation warnings, and `make check` passes.

### M3: Import pipeline and persistence (M), done

Merchant and Store move here from v1 Milestone 4, because receipts
depend on them. Scope trimmed on 2026-11-14 (D21, see the M3–M6
simplification notes below).

**Tasks**

1. Models and migrations: `Merchant`, `Store`, `Receipt`, `ReceiptItem`
   (product FK and its check constraints added in M4) and
   `ReceiptImportJob`, with the constraints and indexes in §8 and
   TD §8.2. Receipt columns cover only what is filtered or aggregated;
   everything else goes to `Receipt.source_data`. Add
   `apps/common/fields.py` (money and quantity field factories).
2. `receipts/classification.py`: the four line types (§9.1) from
   keyword constants.
3. `services/persistence.py`: merchant upsert by VAT, store resolution
   by branch number then address, and receipt plus items in one
   transaction with the job completion (§6.6). Identity-duplicate
   handling (outcome `duplicate`). Product lines are stored as
   `needs_review` until M4.
4. `tasks.py` and `services/pipeline.py`: the claim with
   `SKIP LOCKED` and a lease on `next_attempt_at`, the three job states,
   error-code mapping, and the single retry schedule (§6.4, §6.5,
   TD §12.2–§12.4). The `worker` and `beat` services already run.
5. Import API: `POST /receipts/import` (every response case in §6.2,
   race-safe uniqueness), `GET /receipt-imports[/{id}]`, and
   `POST …/retry`. Throttles.
6. Basic `GET /receipts`, `GET /receipts/{id}`, `PATCH` and `DELETE`
   (D10).
7. Beat task `run_due_imports` (every minute).
8. Admin for all models, with a "retry import" action and list filters
   on job status, provider and error code.

**Tests:** import API cases, concurrent duplicate submission (two
transactions), task re-execution idempotency, the lease (double claim,
expired lease, attempts exhausted), rollback on a failure injected
during persistence, the retry schedule, deletion then re-import, and the
end-to-end acceptance test (§18) steps 1–2 and 4–7.

**Exit:** a real URL submitted through the API (opt-in live run) becomes
a stored receipt visible in the API and the admin. A failed import is
visible and retryable.

### M4: Products, matching and price history (M), done

**Tasks**

1. Models: `ProductCategory` (flat) with a seed data migration,
   `Product` and `MerchantProductMapping`. Add the `ReceiptItem.product`
   FK and its check constraints.
2. `units.py` and `packages.py`: unit vocabulary, conversions and
   package-size suggestions (§9.4).
3. `matching.py`: mapping lookup by code or description, the code-reuse
   guard (`difflib`), and auto-creation (§9.2).
4. `prices.py`: `refresh_prices()` and the `PRICE_HISTORY` filter
   (§11.1, TD §13.4).
5. Wire matching and price refresh into the pipeline transaction. A
   `backfill_matching` command for receipts imported in M3.
6. `review.py`: link, create product from a line, reclassify, merge.
7. Review and product APIs (§12.6, §12.7): review list, match,
   create-product, PATCH line, product CRUD, merge, prices,
   price-comparison.
8. Admin: products, mappings, categories, merchant default category,
   and "re-run matching" / "recompute prices" actions.

**Tests:** every matching step and outcome, the code-reuse guard, the
concurrent new-item race, a link remembered on the next import, merge
(moves lines and mappings, deletes the sources, refreshes prices), price
refresh on every trigger, every normalization case, the comparison
`comparable:false` cases, isolation-matrix additions, and E2E step 3.

**Exit:** importing the sample twice from different "merchants" in
tests, then merging the products, produces a correct cross-merchant
price comparison.

### M5: Query APIs and analytics (M), done

**Tasks**

1. Receipt filters, search and ordering (§12.5), and product filters
   with substring search (§12.7).
2. Merchant, store and category endpoints scoped to the household's own
   receipts (§12.8). Household category CRUD.
3. Analytics queries and endpoints (§12.9, §13): summary with the
   previous-period comparison, by category (with the merchant
   default-category fallback), by merchant, monthly trend, top products.
4. Performance: `select_related` and `prefetch_related` on every list,
   query-count tests, and a `seed_demo_data` command.

**Tests:** filter and pagination tests, the bucket-sum invariant, the
merchant-category fallback, the timezone month boundary, credit-note
and cancellation effects, the full isolation matrix over every endpoint,
and query-count limits.

**Exit:** the OpenAPI schema covers everything a frontend or the
Android app needs for the dashboard, receipt, product and review screens.

### M6: Operations hardening (S)

**Tasks**

1. A test asserts that no full receipt URL ever appears in captured
   logs during an import (logging and redaction exist since M1).
2. Optional Sentry with PII scrubbing.
3. `compose.prod.yaml`: the `prod` image target (gunicorn, non-root
   user), the `proxy` service (Caddy, HTTPS for `$DOMAIN`), `restart:
   unless-stopped`, and only the proxy published. Worker egress
   guidance.
4. The `backup` service (`ops/backup.sh`: daily `pg_dump`, 30-day
   rotation) and `make backup` / `make restore`, with a tested restore
   procedure in the docs.
5. A security pass: run `/security-review` on the code base, check the
   dependency audit, check the settings with `manage.py check --deploy`.
6. Docs: deployment, recovery, a runbook for provider format changes
   (reproduce with `make parse-receipt`, then the `add-provider` skill).

**Exit:** all acceptance criteria in §19 pass. The deferred frontend can
start against a stable API.

### M3–M6 simplification (2026-11-14, D21)

A review after M2b found that the code built so far is sound, but the
planned M3–M6 design was sized for a multi-tenant service rather than
one household. It was trimmed before any of it was built:

| Removed or reduced | Replaced by |
|---|---|
| Six job states, two retry counters, three retry schedules | `pending` / `completed` / `failed`, one `attempt_count`, one schedule |
| `client_request_id`, `client_metadata`, `idempotency_key_mismatch` | URL identity uniqueness (already idempotent) |
| Stuck-job sweeper, compare-and-set transitions | a lease on `next_attempt_at` set by the claim |
| `ReceiptSourceSnapshot` and its purge task | `make parse-receipt SRC=<url>` while the link works |
| `UnsupportedHostCounter` | a log line with the host |
| Import-job purge after 365 days | jobs kept (small); add a purge later if needed |
| `LineClassificationRule` table; 7 line types; line-type source | keyword constants; `product` / `discount` / `fee` / `other` |
| Six extra myDATA amounts as columns on receipts and lines; many label/code columns | `Receipt.source_data` JSON |
| `review_status`, `validation_status` columns | computed from lines / from `validation_warnings` |
| Five match statuses, seven match methods, confidence, fuzzy candidates, `pg_trgm` | `matched` / `needs_review` / `not_a_product`; substring search |
| Product `status`/verify, barcode, sale unit, `merged_into`, `is_active`, package source | merge deletes the sources; barcodes added when a source prints them |
| `remember` flag, unmatch and mapping-delete endpoints | linking always updates the mapping |
| `ProductMergeLog` | nothing (merging is explicit and rare) |
| `ProductPriceObservation` projection and its sync | three normalized-price columns on `ReceiptItem` |
| Category tree | flat categories, plus the merchant's default category as the main category source for spending |
| `price-changes` analytics | product price history |
| Staff `import-stats` endpoint and drift dashboard | admin list filters and logs |

## 3. Cross-cutting rules for every milestone

- Tests are written alongside each feature. CI-equivalent checks run
  in containers through `make check` (ruff, format,
  `makemigrations --check`, pytest). Nothing runs on the host except
  Docker and Make.
- No live network in tests, except tests marked `live`.
- Migrations are reviewed and kept forward-only after the first
  deployment.
- `docs/` stays current. Any deviation from the requirements is recorded
  there.

## 4. Dependencies and order

```text
M1 ──► M2 ──► M3 ──► M4 ──► M5 ──► M6
        ▲
   more receipt
    samples
```

M2 can start right after M1. Its pure parsing and fetching code does
not depend on the database models.

## 5. Open items

All product decisions (D1–D18) were confirmed on 2026-11-13.

**Resolved**

| Item | Answer |
|---|---|
| Android client | Built later. It adopts this server's API (D17) |
| More receipt samples | Added when available. M2 starts with the sample and synthetic variants |
| Git | Initialized manually by the project owner (D18). CI is added when a remote exists |
| Deployment | Everything dockerized (D16). Production uses `compose.prod.yaml` with Caddy on a single host |

**Waiting on**

Nothing. The owner approved M3 on the trimmed scope (D21) on 2026-11-14.

**Verified during implementation (no input needed)**

| Item | When |
|---|---|
| ~~Check the myDATA code lists against the official AADE documentation~~ Done in M2 (v1.0.9 appendix 8) | M2 |
| ~~Check Impact's terms of use~~ Done in M2: no public terms found; the page labels the link as the recipient's retrieval URL (see `providers/impact.md` §2) | M2 |
| Confirm the R4/R8 total formulas against more receipt samples (the official doc does not state the formula; the sample is consistent) | When samples arrive |

## 6. Status

| Milestone | Status | Date | Summary |
|---|---|---|---|
| M1 Foundation | **Done** | 2026-11-14 | Docker stack (`db`, `redis`, `migrate`, `api`, `worker`, `beat`), `make` workflow, split settings, `common` (error envelope, household scoping, request-context logging with URL redaction, health checks), accounts (email user, JWT with rotation and blacklist, invite-gated registration, throttles, `bootstrap_household`), households (members, invitations), OpenAPI with Swagger UI. `make check`: 117 tests, 99% coverage. The production image builds and passes `check --deploy` |
| M2 Provider | **Done** | 2026-11-14 | Pure receipt layer with no database: canonical dataclasses, verified myDATA code tables, strict culture-aware number and date parsing, text normalization, URL validation, provider registry, SSRF-safe fetcher (pinned IP + SNI, no redirects, decompressed size cap, deadline), Impact parser (two views cross-checked, personal data never read), validation rules R4–R12, `parse_receipt` and `sanitize_impact_fixture` commands. Sanitized real fixtures in both cultures with golden files, plus synthetic variants. `make check`: 311 tests, 98% coverage. The live run against the real receipt passes |
| M2b More sources | **Done** | 2026-11-14 | Built for new formats: page layouts per provider, shared label vocabularies, coverage flags and notices on every receipt, per-provider sanitizers, fetcher status hand-off, auto-discovered fixtures with meta files. New providers: Entersoft (two-step fetch, real line discounts) and the AADE cash-register check page (summary-only, signature-mismatch notice). 10 real-page fixtures across 3 providers. `make check`: 390 tests, 97% coverage. Live runs pass for all 4 real links |
| M3 Pipeline | **Done** | 2026-11-14 | `merchants` app (merchant and store resolution, details refreshed from newer receipts), import jobs, receipts and lines with the identity constraints, keyword line classification, the import pipeline (claim with `SKIP LOCKED` and a lease, one retry schedule, error-code mapping, persistence in one transaction), `run_due_imports` on beat, import and receipt APIs, admin with a retry action. Tested end to end with all three providers' fixtures, including real concurrent transactions. `make check`: 548 tests, 98% coverage. Live runs pass for all 4 real links (Impact, 2 Entersoft, AADE), from API submission to the stored receipt |
| M4 Products | **Done** | 2026-11-14 | `products` app (system categories seeded, household products, merchant item mappings), package-size parsing, matching with the code-reuse guard and auto-created products, normalized prices on receipt lines, review services (link, create from a line, reclassify, edit, merge), product, price-history, comparison and review APIs, admin actions, `backfill_matching`. Tested on every real fixture line (LIDL's reused and repeated codes included), with a real two-thread race for a new item. `make check`: 660 tests, 98% coverage |
| M5 Query and analytics | **Done** | 2026-11-14 | Receipt filters and search (EXISTS subqueries, no duplicate rows), merchant and store endpoints scoped through the household's receipts, household categories (system ones read-only), analytics (summary with the previous period, spending by category with the merchant fallback and the bucket-sum invariant, by merchant, monthly trend in the household timezone, top products), `seed_demo_data`, `X-Household-ID` documented on every scoped operation. `make check`: 719 tests, 98% coverage |
| M6 Operations | **Done** | 2026-11-15 | `compose.prod.yaml` (Caddy HTTPS, restarts, JSON logs, memory limits, Raspberry Pi sizing), `backup` service with 30-day rotation, `make prod-*`, `make backup` / `make restore` (tested), optional Sentry with URL/body/locals scrubbing, the log-secrecy test across all providers, a security pass with fixes (personal data allowlist, API body limit, admin login and retry throttles, `NUM_PROXIES`), `docs/deployment.md`. `make check`: 739 tests, 98% coverage. The production stack was run end to end on arm64 |

### M1 notes and deviations

- **Celery runs from M1.** The `worker` and `beat` services run, with
  one maintenance task (`accounts.flush_expired_tokens`, daily) that M3
  had originally planned.
- **Configurable host ports.** Dev host ports come from `.env`:
  `API_HOST_PORT` (default 8000) and `DB_HOST_PORT` (default 55432, to
  avoid clashing with a local PostgreSQL).
- **One-off Make commands** (`test`, `check`, `manage`, …) start only
  `db` and `redis` and run with `--no-deps`. They do not start the
  `migrate` service, so they work before migrations exist. Tests create
  their own database.
- **Celery logging.** Workers use Django's `LOGGING`
  (`setup_logging` signal, no root-logger hijack), so task logs get the
  same context fields and URL redaction.
- **Registration and invitations:**
  - Registration responses include a token pair, so the app is logged
    in immediately.
  - Logout returns `204`.
  - `DELETE /households/{id}/invitations/{iid}` revokes (sets
    `revoked_at`) instead of deleting.
  - A join attempt by an existing member returns `409 already_member`
    and leaves the invitation usable.
- **Path-scoped household routes.** These routes
  return `404` for non-members, and `403 owner_required` for members on
  owner-only actions. Ownership is checked before input validation.
- **`apps/common/fields.py`** (money field factories) is deferred to M3,
  where the first money fields appear.

### M2 notes and deviations

- **Culture detection.** The culture comes from the page's
  `data-culture` attribute, not from label vocabularies. Tax-view labels
  turned out to be Greek in both cultures.
- **Date order** is fixed per (culture, view). English tax-view dates
  are month/day while English commercial dates are day/month. The two
  are cross-checked.
- **Units.** The official myDATA table defines only units 1–3 (pieces,
  kg, liters), so the unit vocabulary is `piece | kg | l | other` (the
  requirements were updated).
- **Synthetic variants** are generated in code from the real sample
  (`tests/receipts/impact.py`) instead of hand-edited HTML files.
- **`Line.quantity` is optional,** so a missing quantity is not
  invented.
- **Unknown fields.** Values under unknown tax-view payment labels are
  not stored (only the label), because they may be personal.
- **Module names:** `views.py` replaces the planned
  `commercial.py` + `taxview.py`; `links.py` and `errors.py` hold URL
  parsing and the error hierarchy.
- **New Make targets:** `make parse-receipt SRC=…`,
  `make sanitize-fixture IN=… OUT=…`, `make test-live URL=…`.
- **Privacy:** the real receipt's access GUID was removed from
  `docs/providers/impact.md`. Fixtures and tests contain only sanitized
  or fake values; the repo was scanned for the real personal values.

### M2b notes and deviations

- **Canonical model extended:**
  - `Coverage` and `Notice` added.
  - `Document.kind` is set by the provider; `type_code` is optional.
  - `Identity.uid` is optional, and `source_key` is new.
  - `Line.unit` (canonical) and `gross_before_discount` are new.
  - `Payment.method` and `derived` are new.
  - `Totals` gains discount fields.
  - Lines may be empty.
- **Validation:** R5 uses the value before discount. R7 compares only
  fully provided values. R9 also checks net. R11 follows coverage. New
  rules R13–R16, and notices become warnings.
- **Dates** accept `-` and `.` separators and the year-first order.
- **`sanitize_impact_fixture` is replaced** by the generic
  `sanitize_fixture <provider>` (`make sanitize-fixture PROVIDER=…`).
  `make test-live` takes `URLS="…"`.
- **Fixtures:** every real page has a meta file and is tested by the
  generic harness. The Impact golden test moved there.
- **Entersoft:**
  - The store address comes from the receipt (no branch number).
  - The time of issue is the transmission time when it falls on the
    issue date (`approximate`), otherwise midnight (`date_only`).
  - The brand name (`LIDL`) is stored as the merchant name.
- **AADE cash register:**
  - VAT categories Α/Δ/Ε follow the usual mapping (6/36/0%) and are
    checked per receipt by R14. Β = 13% and Γ = 24% are confirmed by
    real data.
  - A remainder after the card amount is recorded as a derived cash
    payment.
  - "Not transmitted (yet)" pages are `receipt_not_found`, so they are
    retried on the long schedule (fuel receipts are transmitted at the
    end of the day).
- **Not in scope:** the AADE myDATA summary page
  (`mydatapi.aade.gr/…QRInfo`) is documented but not used.

### Carried into M3

- Nothing is blocking.
- **Persistence must keep the M2b fields:**
  - as columns on `Receipt`: `source_key` (with its partial unique
    constraint) and `document_kind` (from `canonical.Document.kind`);
  - as columns on lines: `unit` and `discount_amount`;
  - in `Receipt.source_data`: coverage, notices, payments (with
    `method` and `derived`) and each line's `gross_before_discount`.
- **Lines may be empty.** Receipts with zero lines are valid when
  `coverage.line_items` is false.
- **Parsers stay at their `/1` layouts** until real receipts show
  otherwise. New receipts are added with the `receipt-fixture` skill;
  new hosts and formats with the `add-provider` skill.

### M3 notes and deviations

- **New `merchants` app** with `Merchant` and `Store`. It has no API
  yet: merchant and store endpoints are part of M5.
  `Merchant.default_category` is added in M4, with the products app.
- **Merchant and store details** carry `details_as_of`, the issue time
  of the receipt that last set them:
  - Empty fields are filled from any receipt.
  - Filled fields are replaced only by a receipt issued at the same
    time or later.
  - A truncated copy never replaces a value (cash-register pages cut
    long names).
  - The display name is the legal name without its legal form
    (`METRO ΑΕΒΕ …` → `Metro`). It follows the legal name until staff
    edit it.
- **Stores without a branch number** are unique on
  `(merchant, normalized_address)`, so concurrent imports from a new
  store create it once. The key is street, number, postal code and city.
  The country is left out, because sources print it inconsistently.
- **`ReceiptItem` in M3** has no `product` FK and no normalized-price
  columns. M4 adds them with the `item_product_iff_matched` constraint.
  The line-type constraint (`not_a_product` exactly for non-product
  lines) already exists. `description` is a `TextField`, so it is never
  cut. `merchant_product_code` is 100 characters long.
- **Import jobs:**
  - A new `issuer_vat` column, shown by the API. Impact URLs provide it
    before fetching; for other sources it is filled after parsing.
  - A check constraint: only completed jobs have an outcome.
  - `url_identity` is 200 characters long.
  - Resubmitting a failed or deleted import also stores the new link,
    since it may work where the old one did not.
- **API contract** (requirements §6.2 and §12.4 updated):
  - `POST /receipts/import` returns the import representation plus
    `duplicate`. The import id is `id`, not `import_id`.
  - Malformed or oversized JSON returns `400 invalid_request`. DRF's
    `parse_error` code is renamed globally, and a new `handler400`
    answers Django-level 400s (bodies over 16 KB) with the envelope
    instead of an HTML page. A missing `url` field returns
    `400 validation_error`.
  - `POST /receipt-imports/{id}/retry` returns `202` with the import.
  - `next_attempt_at` is shown only while a retry is scheduled. The
    claim lease stays internal.
  - The receipt list supports ordering only (`issued_at`,
    `gross_total`). Filters come in M5. The receipt detail includes
    coverage, the VAT breakdown and payments from `source_data`.
- **Line classification:** a keyword matches the start of a word, and a
  two-word keyword matches two consecutive words (`ΠΕΡΙΒΑΛΛΟΝΤΙΚ ΤΕΛ`
  matches `ΠΕΡΙΒΑΛΛΟΝΤΙΚΟ ΤΕΛΟΣ`). A zero-net line counts as a fee only
  when its net amount is known.
- **Logging:**
  - `RedactFilter` also redacts URLs in tracebacks, because an
    exception message can quote a URL.
  - For an unexpected error, the job stores only the exception class
    name.
- **Isolation matrix:** routes without an object id (lists, create)
  name a household-B id that must not appear in the response
  (`hidden=`).
- **Exit criteria:**
  - A failed import is visible and retryable, in the API and in the
    admin.
  - A real URL submitted through the API becomes a stored receipt: the
    opt-in `test_live_import_through_the_api` (`make test-live URLS=…`)
    passed on 2026-11-14 for all 4 real links (Impact, 2 Entersoft,
    AADE).

### Carried into M4

- Add the `ReceiptItem.product` FK, the normalized-price columns, the
  `item_product_iff_matched` constraint and `Merchant.default_category`.
- Until matching exists, every product line imported in M3 is
  `needs_review`, so those receipts report `needs_review: true`. The
  `backfill_matching` command must cover them.

### M4 notes and deviations

- **`ReceiptItem.product` uses `RESTRICT`, not `PROTECT`.** With
  `PROTECT`, deleting a household fails, because its products are
  referenced by its own lines. `RESTRICT` still refuses to delete a
  product that other lines use, but allows the household cascade.
- **Matching runs before the lines are written:** classify, match,
  compute prices, then one `bulk_create`. `match_item()` sets fields and
  does not save. The lines themselves never wait on a second write.
- **Code mappings follow the item:** each match stores the line's
  description as `last_seen_description` and its key as
  `normalized_description`. The guard compares the normalized forms with
  `difflib` (threshold `MATCH_GUARD_SIMILARITY = 0.4`, a setting).
  Measured on real data: LIDL's two tuna salads under code `6201025`
  score 0.47 (matched: one item for LIDL), an unrelated item 0.19
  (review).
- **Merging needs no key conflict handling.** Mapping keys are unique
  per household and merchant whatever the product, so the sources'
  mappings are simply repointed. TD §13.5 step 2 is gone.
- **Package parsing** (requirements §9.4 updated): a size may follow an
  abbreviation dot (`ΦΥ.Ζ.195G`) but not a decimal one; unit letters
  accept Latin and Greek look-alikes (`ΦΥΛ1ΚG`); `mg` becomes `g`.
  Sizes are suggested only for `piece` lines. Known false positive: a
  bag capacity such as `S.ΣΑΚΟΥΛΕΣ 60L 20Τ` reads as a 60 l package,
  which a person can clear.
- **Corrections:**
  - Linking a line deletes the previous product when it is left with
    no lines and no mappings (a wrong auto-match leaves nothing behind).
  - Reclassifying away from `product` keeps the old product while a
    mapping points at it. Reclassifying back to `product` matches the
    line again.
  - The admin keeps receipt lines read-only apart from the note:
    reclassifying there would bypass prices and mappings. A package
    change in the product admin recomputes prices.
- **API** (requirements §11.3, §12.6 and §12.7 updated):
  - Review routes live in `apps/products/api` (`receipt-items/...`).
    `match` and `PATCH` answer `200` with the line; `create-product`
    answers `201` with the line. A non-product line answers
    `409 not_a_product_line`.
  - `GET /products/{id}/prices` is paginated and adds `stats` for every
    entry that matches the filters (not just the page).
  - `GET /products/{id}/price-comparison` compares one
    (normalized unit, currency) group: the requested `normalized_unit`,
    else the group with the most entries. `reason` is `no_prices`,
    `one_merchant` or `unknown_unit` (the `other` unit is never ranked).
    `available_units` lists every group.
  - `POST /products/{id}/merge` answers `200` with the target.
  - Products cannot be deleted through the API (not in the contract).
- **Exit criterion:** the same receipt stored for two merchants, then
  the two milk products merged, gives a ranked comparison
  (`test_cross_merchant_comparison_after_merging`).
- `apps/common/text.normalize_text` is reused for product names and
  search keys. Product names are cut at 255 characters (descriptions
  are never cut).

### Carried into M5

- Category endpoints (`GET|POST /categories`, `PATCH|DELETE
  /categories/{id}`) and the merchant and store endpoints.
- Receipt filters, including `product` and `category`, and
  `GET /receipts?needs_review=true`.
- Spending by category falls back to `Merchant.default_category`, which
  staff set in the admin (M4).

### M5 notes and deviations

- **Analytics count one currency:** only receipts in the household's
  `default_currency` are included, so amounts in different currencies
  are never added together. The summary reports the others as
  `other_currency_receipts` (requirements §13 updated).
- **Period parameters** (requirements §12.9 updated): no `from`/`to`
  means the current month; `from` alone runs to today; `to` alone starts
  on the first day of its month; `to` before `from` is a `400`. The
  monthly trend takes `to` (a day in the last month) and `months` (1–36,
  default 12); top products take `by` and `limit` (1–50, default 10).
  Every response states its `period` and `currency`.
- **Spending by category** runs three grouped queries (lines by bucket,
  receipts by merchant default category, lines by merchant default
  category) and subtracts the last two per default category in Python,
  so the remainder of every receipt (all of a summary-only receipt)
  lands in its merchant's default category or "Unallocated". A
  randomized test and the real fixtures check that the buckets add up
  to spending.
- **Receipt filters** (requirements §12.5 updated): line conditions
  (`product`, `category`, `needs_review`, `q` on line text) are EXISTS
  subqueries, so a receipt is listed once and its line count stays
  right. `category` also matches receipts from a merchant whose default
  category it is. `q` matches line text accent-insensitively and the
  merchant's display or legal name. `min_total`/`max_total` filter on
  the gross total.
- **Merchants and stores** are shared data, so they are scoped through
  the household's receipts: `HouseholdScopedMixin.scope_queryset()` is
  the hook (the default filters on `household_lookup`). The lists carry
  the household's `receipt_count` and `last_receipt_at`, computed in the
  same query. There is no store detail route (not in the contract).
- **Categories:** `GET /categories/{id}` exists too. The list is not
  paginated (a flat list of about twenty). Names must be new within the
  household and must not repeat a system category; the slug is derived
  from the name (Greek kept). Changing or deleting a system category is
  `403 system_category`; deleting a category that products use is
  `409 category_in_use`. Any household member may manage categories.
- **OpenAPI:** `apps.common.schema.AutoSchema` documents the optional
  `X-Household-ID` header on every household-scoped operation, and the
  three identical merchant reference serializers became one.
- **`seed_demo_data`** (`make manage ARGS="seed_demo_data --household
  <id>"`) stores deterministic demo receipts through the real
  persistence (matching and prices included): four demo shops (VAT
  `99000000x`) with default categories, a summary-only fuel station,
  occasional credit notes and coupons. It refuses to run without DEBUG
  unless `--force` is given; the same `--seed` twice adds nothing.

### Simplification pass (2026-11-15, after M5)

A whole-codebase pass removed accidental complexity without changing the
API contract, schema, security behavior or parsed output (golden files
unchanged). `make check`: 718 tests, 98% coverage. In summary:

- **Settings are read directly** from `django.conf.settings`.
  `apps/common/conf.py` (`AppSettings`) is gone, and `PAGE_SIZE` is gone
  from settings.
- **Household scoping:** `resolve_household` returns the `Household`,
  and the mixin sets `self.household`. `HouseholdContext` and the unused
  `HouseholdQuerySet.for_household` were removed; scoping goes only
  through `HouseholdScopedMixin`.
- **Providers:** each provider is now one `Provider` record (hosts,
  layouts, and the functions of its `urls`/`parser`/`sanitize` modules,
  plus an optional `fetch_document` for multi-step sources). This
  replaces the `ReceiptProvider` protocol, the `BaseProvider` class and
  its subclasses. `ProviderRegistry` takes its providers in its
  constructor, `resolve_url` is its single entry point, and
  `build_registry` is gone. `ProviderError` was removed, so every error
  subclasses `ReceiptError` directly.
- **Fetcher:** `FetchedDocument` keeps only `body`, `status` and
  `charset`; nothing in the app read the other fields. The SSRF
  protections are unchanged and now have comments explaining them.
- **Admin:** the user admin uses Django's creation and change forms and
  keeps only the case-insensitive email check.
- **Smaller cleanups:**
  - Dead constants and properties were removed: myDATA code tables and
    label entries nothing read, `retry_scheduled`,
    `SubmitResult.duplicate` and `parser_version`.
  - Duplicate helpers and serializer fields were merged.
  - The merchant list joins only the household's receipts.
  - Comments now explain the non-obvious rules: the lease and retry
    behavior, savepoints, the code-reuse guard, the bucket-sum
    invariant, timezone handling and owner locking.

### Carried into M6

- The test that no receipt URL reaches the logs during an import
  (redaction covers messages and tracebacks since M3).
- Production compose, backups, Sentry and the security pass, as
  planned.

### M6 notes and deviations

- **Log secrecy test** (`tests/receipts/test_url_secrecy.py`):
  - It reads what the configured `stdout` handler actually writes, not
    `caplog`, which sits beside the redaction filter.
  - It covers API submission plus the inline task for Impact, Entersoft
    and AADE, a provider error and an unexpected error that quote the URL
    (tracebacks included), and a rejected link.
  - It checks the URL, its path and query, and each long token in them.
  - The raw records of successful imports carry no URL either: the code
    logs host and fingerprint, and the redaction filter is only a safety
    net.
- **Sentry** (`apps/common/sentry.py`):
  - Scrubbing goes beyond the plan: no local variables, no request
    bodies, query strings, cookies or sensitive headers, and URL
    redaction in events and breadcrumbs.
  - Events are tagged from the log context (the pipeline now binds
    `provider`). There is no `error_code` tag: unexpected errors are
    always `internal_error`.
  - `send_default_pii` is not passed, because sentry-sdk 2.x deprecates
    it; its default is off.
  - `RedactFilter` now keeps `exc_info` on log records, so Sentry still
    gets stack traces. Formatters print the redacted `exc_text`, and
    `apps.common.logging.JsonFormatter` redacts the tracebacks it formats
    itself.
  - Verified with an in-memory transport, not against a real Sentry
    server.
- **Production compose** (`compose.prod.yaml`, `ops/Caddyfile`):
  - **Network model** (owner decision, 2026-11-15): Eksoda is reachable
    only on the home network and through the VPN (PiVPN/WireGuard on the
    Pi), never from the internet.
    - Caddy uses its own local CA (`tls internal`) instead of Let's
      Encrypt.
    - `make prod-ca` exports the root for client devices.
    - Clients use a Pi-hole local DNS name such as `eksoda.lan`.
    - Caddy listens on the published port numbers. An explicit HTTP
      redirect keeps a non-standard HTTPS port, which Caddy's automatic
      redirect dropped in the trial.
  - The proxy's host ports are configurable (`HTTP_PORT`, `HTTPS_PORT`),
    because the target Raspberry Pi already runs Pi-hole on 443.
  - Process counts are configurable (`WEB_CONCURRENCY` 2,
    `CELERY_CONCURRENCY` 1) and every service has a `mem_limit`.
  - Redis has a 64 MB `volatile-lru` cap, and Docker logs rotate.
  - Caddy has no active health check: it sent `Host: api:8000`, which
    `ALLOWED_HOSTS` rejects, and made every request a 503 in the trial
    run.
  - `LOG_FORMAT=json` is fixed in the production compose, because
    `.env.example` says `console`.
  - **Trial run on arm64** (Apple Silicon, the same architecture as the
    Pi), with `DOMAIN=localhost` and Caddy's local CA:
    - all services healthy; HTTP redirects to HTTPS; HSTS set
    - Swagger answers 403 to anonymous users; static files are served
    - a 20 KB API body gets a 400, a 2 MB body a 413 at the proxy
    - bootstrap and login work through the proxy
    - `check --deploy` is clean
    - about 400 MB of RAM in all
  - Second trial run with the local CA, as `eksoda.lan` on 8081/8443:
    - HTTPS verifies against the exported root; without it, it fails
    - HTTP redirects to `https://eksoda.lan:8443/…`
    - the root survives recreating the proxy
    - the admin login form works with `DJANGO_CSRF_TRUSTED_ORIGINS` set
  - The deployment on the Pi itself is not verified yet.
- **Backups** (`ops/backup.sh`):
  - A shell loop, not cron. Every 10 minutes it takes the day's dump if
    none exists after `BACKUP_HOUR_UTC`, so a dump missed while the
    service was down is caught up. Dumps are written under a temporary
    name, then renamed.
  - The service starts after `migrate`, so its first dump is never of an
    empty database.
  - `make restore` needs `CONFIRM=yes`. It takes a safety dump, then
    drops and recreates the database instead of using `pg_restore
    --clean`, so tables from newer migrations cannot survive a restore.
  - **Restore test** (dev stack): 150 receipts, 428 lines and 15
    products were dumped, 100 receipts deleted, and the dump restored;
    all rows came back.
  - The pruning loop was tested on the backup image: a 45-day-old dump
    was deleted and a 26-day-old one kept.
- **Security pass:**
  - `/security-review` works on a git diff, and this checkout is not a
    git repository. An independent full-codebase review (read-only
    subagent) took its place, plus `pip-audit` on the locked runtime
    dependencies (no known vulnerabilities) and `check --deploy` with
    production settings. `security.W021` (HSTS preload) is silenced,
    because preload is a per-domain decision.
  - Fixed:
    - **Personal data (§15.3).** The Impact payload kept whole sections,
      including the free-text miscellaneous one, and every provider
      stored the values of unknown fields in `source_data`. The payload
      now keeps only known fields (the Impact golden files lost only
      `misc`), `source_data` keeps unknown fields by name only, and
      Luhn-valid card-number runs are dropped from payment labels.
    - **Body limit.** The 16 KB limit did not apply to DRF, which reads
      the stream directly. `LimitedJSONParser` is now the default
      parser, and line notes are capped at 2000 characters like receipt
      notes.
    - **Throttles.** Import retries count against the import limits, and
      the admin login is throttled per IP (`THROTTLE_ADMIN_LOGIN`,
      5/min).
    - **`NUM_PROXIES = 1` in production,** so throttles use the address
      Caddy saw and not a client-supplied `X-Forwarded-For`.
  - **Docs:** `docs/deployment.md` (deployment, Raspberry Pi notes,
    updates, backup and restore, monitoring, security notes, the
    format-change runbook). The README and TD §3, §16 and §17 are
    updated.

### Carried after M6

- **Deployed to the Raspberry Pi on 2026-11-15**, as `https://eksoda.lan:8443` (HTTP on 8081).
  - **What runs:** all services are healthy. The worker resolves the provider hosts, and logs are JSON.
  - **Tested there:** the daily dump, `make backup PROD=1`, and `make restore PROD=1` on the still-empty database.
  - **Fixes from the deployment:**
    - the build runs on the host network (Pi-hole dropped DNS from the build container)
    - the backup service gives the directory and the dumps to `BACKUP_OWNER` (they were root-owned, so `make backup` and `make restore` failed for the host user)
    - manual dumps are mode 600
  - **Still to do on the host (owner):**
    - enable the cgroup memory controller (memory limits are ignored until then)
    - add the Pi-hole local DNS record `eksoda.lan`
    - bootstrap the first owner
    - install the root CA on client devices
    - prefer an SSD, or at least off-host backup copies
- Android app: its release network security config must trust the
  server's local CA (`docs/android-app.md` §10). Until then, the release
  build cannot reach the server.
- Two review notes left open:
  - NAT64/6to4 address forms are not in the fetcher's blocklist. This
    is theoretical: the allowed hosts are fixed.
  - No test covers revoking a refresh token obtained from `/auth/refresh`
    after a password change.

