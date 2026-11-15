# Review of the original requirements (v1.0)

**Date:** 2026-11-13
**Inputs:** the original `requirements.md` v1.0 (removed 2026-11-13 after v2 replaced it), plus a live inspection of the sample
Impact receipt (see `docs/providers/impact.md`).
**Output:** The issues below are resolved in `docs/requirements.md`.
Each item names the section of v2 that addresses it.

Overall, v1 is a strong document. Its principles (preserve source data,
traceability, conservative matching, idempotency, SSRF awareness) are
right and are kept. The problems are mostly about (a) facts the authors
could not know without inspecting a real receipt, (b) internal
inconsistencies, and (c) decisions that were left open but block
implementation.

## 1. What the real receipt changes

| Finding | Why it matters |
|---|---|
| The page is static server-rendered HTML with **two views**: commercial and AADE myDATA tax view | We can cross-validate two views of the same data. This gives a strong, cheap way to detect format changes |
| Every certified Greek provider sends the **same myDATA data** to AADE | The canonical model should follow myDATA (document types, VAT categories, unit codes, payment codes, MARK). Adding more providers then becomes a parser-only job |
| **MARK** (AADE registration number) and **UID** identify each receipt nationally. The URL already contains the issuer VAT and UID | Gives a stable, provider-independent receipt identity and allows duplicate detection before fetching |
| **Unit price is VAT-inclusive**, while line net and VAT are given separately | v1's check "quantity × unit price = line amount" is undefined. It only holds against the *gross* amount |
| "Not found" returns **HTTP 200** | Error handling cannot rely on status codes |
| Number and date formats **depend on a culture cookie** (`0,622` vs `0.622`) | A careless parser could silently misread amounts. The fetch must be cookie-less and the parser culture-strict |
| Descriptions are **capped at ~40 characters**, mix Latin and Greek letters, and have **no barcodes** | Matching must rely on merchant product code plus confirmed mappings. Barcode-first matching (v1 §8.1) does not apply to this provider |
| **Branch (installation) number** is present | A stable store identity. v1's `provider_identifier` is not needed |
| The issuer is a **legal entity** that can run several retail brands | v1 §7.4 conflates "business" and "brand" |
| Receipts carry a **customer/loyalty code, card transaction ID and POS terminal ID** | Concrete personal data that must be dropped at parse time |
| myDATA totals include **fees, withheld taxes, other taxes, stamp duty, digital transaction fee and deductions**, not only VAT | `gross = net + VAT` is not true in general. The model and validation must include these amounts |
| A receipt can later be **cancelled** (cancellation MARK). Retail **credit notes** (type 11.4) exist | v1 mentions "refunds" but has no document types or cancellation handling |

## 2. Critical issues (wrong data or rework if not fixed)

**C1. Unit price basis is undefined.** v1 §9.2 compares quantity × unit
price with "line amount" without saying which amount. Impact unit prices
include VAT. → v2 §8.7 adds `unit_price_basis`, and §10.2 validates
against gross.

**C2. Milestones are in the wrong order.** Receipts are persisted in
Milestone 3, but `Merchant` and `Store`, which receipts reference by
foreign key, are only created in Milestone 4. → Merchant and Store move
to Milestone 3 in the plan.

**C3. Duplicate detection runs before the receipt identity is known.**
v1 §5.4 deduplicates at step 2, but the provider receipt identifier only
exists after parsing. → v2 §6.3 uses two phases: a URL-derived identity
before fetching, and MARK/UID uniqueness enforced by database
constraints after parsing.

**C4. `needs_review` is used as an import status.** This mixes up "the
receipt was ingested" with "some products are not yet matched". A
receipt with one unknown product would never be "completed", and v1
does not say whether it counts in analytics. → v2 §6.4 limits the import
job lifecycle to ingestion. Product review is a separate status on the
receipt and its lines. Ingested receipts always count in spending
totals.

**C5. The product catalog has no owner.** §4.4 forbids a global product
catalog, but `Product`, the description mappings and `ProductCategory`
have no `household_id`. → v2 §8 scopes products and mappings to the
household. Categories are either system or household.

**C6. Error handling assumes HTTP semantics that the provider does not
follow** (the not-found page returns 200). → v2 §7.3 classifies pages
by content.

**C7. Locale-dependent parsing is not addressed.** → v2 §7.3 requires a
cookie-less fetch and strict, culture-detected parsing.

**C8. The receipt identity key is not specified.** v1 says "add
appropriate uniqueness constraints" without naming the key. → v2 §6.3
uses MARK, with a fallback of (issuer VAT, UID).

**C9. Duplicate semantics across households, and the 409 response.**
Returning 409 "already exists" for a URL that *another* household
imported would leak that the receipt exists. v1 also allows "409 or
return existing" without choosing. → v2 §6.2 makes uniqueness
per-household. Resubmitting returns `200` with the existing import, and
409 is never used for imports.

## 3. Gaps (missing requirements)

| # | Gap | Resolved in v2 |
|---|---|---|
| G1 | No way to choose the household for a request, even though 403 "household" is listed | §12.2 `X-Household-ID` header |
| G2 | The MVP supports several members, but there are no membership or invitation endpoints | §5, §12.3 |
| G3 | Endpoints are missing for: the list of imports (needed to review failed imports), stores, households, product merge, price changes (needed by the dashboard), health checks | §12 |
| G4 | No handling of cancelled receipts or credit notes in the model or analytics | §8.6, §13 |
| G5 | Fees, withheld taxes, other taxes and deductions are missing from the model | §8.6, §8.7, §10 |
| G6 | "Receipt not yet published" timing: a QR scanned at the checkout may not be available yet | §6.5 retry schedule |
| G7 | No household timezone, so month boundaries for analytics are undefined | §8.2, §13 |
| G8 | Editable fields for `PATCH` and the deletion rules are undefined | §12.5, §12.6, §15.4 |
| G9 | Personal data on receipts and retention periods are not defined concretely | §15.3, §15.4 |
| G10 | The registration policy (open or invite-only) and password reset are not decided | §4 D2, §12.1 |
| G11 | No distinction between legal entity and brand. No store identity key | §8.4, §8.5 |
| G12 | "Average price" and "notable price change" are not defined | §11.3, §13 |
| G13 | Categories cover groceries only, but QR receipts also come from restaurants, pharmacies and fuel stations | §8.9 |
| G14 | Stuck-job recovery and retention purging need scheduled tasks, but v1 §15.2 says Celery beat is optional | §14 |
| G15 | Package-size parsing from descriptions is ambiguous (`27/250ML`) | §9.4 |
| G16 | Greek text normalization is missing (accents, final sigma, Latin/Greek look-alike letters, truncation) | §9.5 |
| G17 | No error response format | §12.1 |
| G18 | No visibility into which unsupported providers users try to scan | §16 |
| G19 | No way to rebuild price observations after a product merge or rematch | §11.1 |

## 4. Simplifications

| # | Change | Reason |
|---|---|---|
| S1 | Merge the `parsing` and `normalizing` job states into `processing` | These are fast in-process steps. Separate states add no operational value |
| S2 | Drop `Merchant.provider_identifier` and `Store.provider_identifier` | VAT number and branch number are better identities |
| S3 | Treat `ProductPriceObservation` as a derived projection that can be rebuilt | Avoids drift when lines are rematched or products are merged |
| S4 | Do not keep raw HTML for successful imports. Keep a structured, personal-data-free extraction instead. Keep raw HTML only for failed imports, for 30 days | Privacy. The page can be fetched again from the stored URL |
| S5 | Do not follow redirects | Impact does not redirect. This removes redirect revalidation, an SSRF risk area |
| S6 | Use the Django admin as the interim operations and review UI | The user-facing frontend (§12 of v1) is deferred in this phase |
| S7 | Auto-create an *unverified* household product for each new merchant item code | Price history works from the first repeat purchase without manual work. This is not a merge, so it does not break the "no uncertain merges" rule. **Needs your confirmation (D7)** |

## 5. Minor issues

- v1 mixes British and American spelling ("flavours", "litre"). v2
  uses American English.
- The v1 unit list includes `mg` but not the myDATA units `m`, `m²`
  and `m³`. v2 aligns the units with myDATA codes.
- The v1 §10.4 path `/product-matches/review` lives next to
  `/receipt-items/...`. The path is kept for continuity.
- The v1 §16.4 acceptance test does not cover cancelled receipts or
  culture variants. Both are added.
- Precision and scale for money, quantity and unit price are not chosen.
  → v2 §10.1.
- `ReceiptImportJob` has no `next_attempt_at` or outcome field, so a
  scheduled retry cannot be shown to the user. → added in v2.
