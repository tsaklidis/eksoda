---
name: add-provider
description: Add support for a new receipt source (a new e-invoicing provider host, an AADE page, or a new page layout of an existing provider) to Eksoda's receipt import. Use when the owner sends a receipt link from an unsupported host, when a provider changes its page format (provider_format_changed errors / format drift), or when asked to support a new receipt type.
---

# Add a receipt source or a new layout

The architecture is built so this touches **only**
`backend/apps/receipts/providers/`, the shared vocabularies, fixtures and
docs. If you find yourself changing models, the pipeline or the API, stop:
the canonical model (`apps/receipts/canonical.py`) is missing something.
Extend it deliberately and update `docs/requirements.md` §7.2.

Receipt links work like passwords. Keep raw pages in a scratch directory
**outside the repo**, never paste full links into docs or commits, and
mask them in any output.

## 0. Decide which case this is

| Situation | Do |
|---|---|
| New host (unsupported provider) | Steps 1–8 |
| Known provider, page changed (`provider_format_changed`, `unknown_fields` growing) | Steps 1–2, then add a **new layout** (step 4b) |
| Known provider, new receipt variant that already parses | Only the `receipt-fixture` skill |

## 1. Inspect (read-only)

1. Fetch the page into scratch. Look at status, content type, size,
   redirects and cookies.
2. Find where the data is: static HTML, an iframe or second request on
   the **same host**, or embedded JSON. Never use an endpoint the page
   does not use itself.
3. Probe **once** what a missing or invalid receipt looks like (alter
   one character of the token). Many sources answer 200 or an odd status
   (Entersoft: 418).
4. List every field, with a real example and its canonical target. Mark
   personal data (buyer, loyalty, card or transaction ids, signatures,
   tokens) and anything that encodes the link (QR images, titles).
5. Check the arithmetic on the real data: line math, Σ lines = total, VAT
   breakdown, payments.

## 2. Document

Create `docs/providers/<code>.md`, using `entersoft.md` and `aade.md` as
templates:
- URL format (redacted)
- response behavior, including not-found
- field table
- what is missing compared with the canonical model, and how each gap is
  handled
- personal data and the action for each item
- traps

Add the host to requirements §3.2 if needed.

## 3. Code: `backend/apps/receipts/providers/<code>/`

| File | Contents |
|---|---|
| `urls.py` | `recognize(url) -> UrlIdentity \| None`. A strict regex, nothing unknown accepted. Canonical URL. `identity` = the most stable pre-fetch key (`<code>:<id>`) |
| `parser.py` | One or more `Layout` classes (`name = "<code>/<n>"`, `matches(soup)`, `parse(soup, identity)`), `LAYOUTS` (newest first), `parse_html()` that raises `ReceiptNotFound` for not-found pages and then calls `parse_with_layouts` |
| `sanitize.py` | Use `Secrets` to replace values where they occur: `replace_element` (any length), `replace_attribute`, and `replace_pattern` for tokens inside links. Never search-and-replace the whole page. Call `strip_active_content`, then `finish` (it verifies, and fails on any leak) |
| `__init__.py` | `provider = Provider(code=..., hosts=..., layouts=LAYOUTS, recognize=..., parse_html=..., sanitize=...)` (`providers/base.py`). Pass `fetch_document=` only for multi-step sources (see `entersoft/__init__.py`) |

Then add `<code>.provider` to the `registry` in `providers/__init__.py`.

**Parser rules:**
- **Pure Python only:** no Django imports (`tests/test_architecture.py`
  checks this).
- **Find fields by label,** `data-*` attribute or CSS class, never by
  position alone. Use `providers/html.py` (`label_map`, `key_of`,
  `amount`, `required`).
- **Map labels through `apps/receipts/vocabulary.py`.** Extend its tables
  rather than hard-coding. Unknown labels go to `unknown_fields`
  (drift), not to an exception.
- **Never read personal blocks,** not even to discard them later.
- **Fail visibly:**
  - A missing required field means `FormatChanged`.
  - Contradictions mean `InconsistentSource`.
  - With a single rendering, enforce the receipt's own arithmetic
    (Σ lines = total, VAT analysis = totals) as fatal.
- **Set `Coverage` honestly:** line items, line tax amounts, official
  codes, myDATA registration, issue-time precision, cross-checked.
- **Report conditions the user should see** (e.g. a signature mismatch)
  as `Notice`s. They become validation warnings.
- **Odd statuses** the provider uses for "not found": pass
  `accept_statuses` to the fetcher and interpret them in `fetch`.
- **Follow-up requests** stay on the same allowlisted host and must point
  to the same document (check its ids). Otherwise raise
  `InconsistentSource`.

### 4b. A new layout of an existing provider

Add `<Name>LayoutV<n+1>` with its own `matches()` and put it **first** in
`LAYOUTS`. Keep the old layout so old fixtures keep passing. Bump the
version in the layout `name`.

## 5. Fixtures (no test code needed)

For each real page:

```bash
make sanitize-fixture PROVIDER=<code> IN=/abs/scratch/raw.html OUT=tests/fixtures/<code>/<name>.html
```

Then:
1. Write `tests/fixtures/<code>/<name>.meta.json`:
   `{"url": "<sanitized url>", "description": "...", "expect": {"warnings": []}}`.
   For pages that must fail, use
   `"expect": {"error": "receipt_not_found"}`.
2. Generate the golden file:
   `make test ARGS="tests/receipts/test_fixtures.py --update-golden"`.
3. Review `expected/<name>.json` line by line against the page.
4. Grep the fixtures and golden files for every real secret you noted in
   step 1. The output must be empty.

Include a not-found fixture and, if the provider has one, a fixture of
its other edge pages.

## 6. Tests: `tests/receipts/providers/test_<code>.py`

URL shapes (good and bad); fetch with a fake fetcher (follow-ups,
not-found statuses, wrong ids); personal data never extracted (inject
`SENTINEL` values and assert their absence); arithmetic failures;
unknown labels becoming drift; sanitizer on raw-like pages.

## 7. Verify

```bash
make check
make test-live URLS="<real url> …"  # the owner's real links, opt-in
make parse-receipt SRC=tests/fixtures/<code>/<name>.html
```

## 8. Record

- Update `docs/implementation-plan.md` §6 with the status and
  deviations.
- Update the provider list in `docs/requirements.md` and in this
  repository's `CLAUDE.md` if it changed.
