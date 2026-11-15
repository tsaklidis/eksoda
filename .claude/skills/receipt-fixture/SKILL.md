---
name: receipt-fixture
description: Add a new real receipt from an already supported source (Impact, Entersoft, AADE cash-register page) to Eksoda's test fixtures - sanitize personal data, add the meta file, create and review the golden canonical JSON, and record newly seen formats in docs/providers/. Use when the owner supplies a new receipt link or saved page from a supported host. For unsupported hosts or changed page formats use the add-provider skill instead.
---

# Add a real receipt as a test fixture

New real receipts are the main way parsers get more robust. Treat the raw
page as **personal data** until it has been sanitized. Supported
providers are listed by `registry.codes`: `impact`, `entersoft`,
`aade_fhm`.

## 1. Get the page (the raw page stays out of the repo)

- See what the parser makes of it:

  ```bash
  make parse-receipt SRC="<url>"
  ```

  This uses the safe fetcher and never touches the database.
- Save the raw HTML **outside the repository**, e.g. in a scratch
  directory. For Entersoft, save the **document** page that the shell
  frames (`/api/GetInvoice?…`), not the shell.
- **Never** paste the raw URL into docs, commit messages or logs.

## 2. Sanitize

```bash
make sanitize-fixture PROVIDER=<code> IN=/abs/path/raw.html OUT=tests/fixtures/<code>/<name>.html
```

- Name the fixture after what is special about it, e.g.
  `credit_note_sklavenitis`.
- The provider's sanitizer replaces personal values and tokens with
  fakes, and refuses to write if any original remains.
- Grep the output for the real values you saw (customer, card ids,
  tokens). There must be no hits.

## 3. Meta file

Create `tests/fixtures/<code>/<name>.meta.json`:

```json
{"url": "<the URL with its token replaced exactly as the sanitizer did>",
 "description": "what this receipt shows",
 "expect": {"warnings": []}}
```

- The sanitized URL matches what the page now contains:
  - Impact: GUID → 32 zeros.
  - Entersoft: document UUID →
    `00000000-0000-4000-8000-000000000000`; token → digits `0`, letters
    `x`.
  - AADE: keep the register and sequence, set the signature part to
    zeros.
- If the receipt legitimately triggers warnings, list their codes. If
  the page must fail, use `"expect": {"error": "<code>"}`.

## 4. Golden file

```bash
make test ARGS="tests/receipts/test_fixtures.py --update-golden -k <name>"
```

Review `tests/fixtures/<code>/expected/<name>.json` line by line against
the page. Check amounts, line count, units, discounts, VAT, identity,
coverage and payments. No test code is needed: the harness discovers the
meta file.

## 5. New formats

If something new appears (codes, line types, labels, a discount style):

- Extend `apps/receipts/vocabulary.py` or `apps/receipts/mydata.py`, or
  the parser, with a focused test.
- Remove any synthetic variant the real fixture now covers.
- Update `docs/providers/<code>.md` ("Unknowns" and the field tables).
- If the page structure changed, follow the `add-provider` skill
  (new layout).

## 6. Finish

`make check`
