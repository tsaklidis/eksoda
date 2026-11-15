# Entersoft e-receipt provider (e-invoicing.gr): observed format

**Inspected:** 2026-11-14. Two real LIDL receipts (21 and 27 lines),
supplied by the owner.
**Status:** Implemented in M2b (`backend/apps/receipts/providers/entersoft/`, layout
`entersoft/1`). Fixtures: both LIDL receipts, the shell page, the not-found page.
Live runs pass on both real links.

Entersoft (ENTERSOFTONE Α.Ε., license
`2020_07_102Entersoft_001_Paperless e-Invoicing_V1_31072020`) is a
certified e-invoicing provider. Its documents go to AADE myDATA like
Impact's do.

## 1. URL format

```
https://e-invoicing.gr/edocuments/ViewInvoice/{ofenm}/{DOC_UUID}_{HASH_TOKEN}
https://e-invoicing.gr/edocuments/ViewInvoice/-1/<uuid, redacted>_<token, redacted>
```

| Segment | Example | Meaning |
|---|---|---|
| `ofenm` | `-1` | Unknown, `-1` in both samples |
| `DOC_UUID` | UUID v4 | Entersoft's internal document id |
| `HASH_TOKEN` | 7–8 lowercase alphanumerics | Access token (the URL is a bearer credential) |

Unlike Impact, the URL carries **no issuer VAT and no UID**. The
pre-fetch identity can only be `entersoft:{DOC_UUID}`. The
provider-independent duplicate check by MARK then happens after
parsing (§6.3 of the requirements already covers this).

## 2. Response

| Step | Request | Response |
|---|---|---|
| 1 | The URL itself | ~3 KB HTML shell (`<title>|Entersoft</title>`). It contains an iframe and a link to the AADE myDATA page |
| 2 | The iframe source on the same host: `/api/GetInvoice?contentType=PEPPOL&intRefDocID={DOC_UUID}&hashToken={HASH_TOKEN}&ofenm={ofenm}&isPreview=True` | ~30–37 KB HTML rendering of the receipt (`text/html`, UTF-8) |

- No redirects. Sets a `cookiesession1` cookie, which is not needed.
- `contentType=PEPPOL` suggests a structured (UBL) variant may exist.
  It is not used, because undocumented endpoints are not probed.
- The shell has a `data-download-token` attribute. It is not needed.

## 3. Fields in the receipt rendering

The markup is Bootstrap columns without semantic classes: label and
value `div`s, plus one items table with fixed Greek column headers.
Numbers use the Greek format (`1,40`, `75,48EUR`).

| Area | Label / column | Example | Canonical use |
|---|---|---|---|
| Header | (first bold line) | `LIDL` | merchant name. This is the **brand**, not the legal entity |
| | (address line) | `2 ΧΛΜ Ε.Ο. ΚΟΖΑΝΗΣ - ΘΕΣ/ΝΙΚΗΣ, -, 50100, ΚΟΖΑΝΗΣ` | store address |
| | `Α.Φ.Μ:` | `093683423` | issuer VAT |
| | (title) | `Απόδειξη Λιανικής Πώλησης` | document type **label only** (no myDATA code) |
| | `Αρ. Παραστατικού:` | `006604-789636` | series-number |
| | `Ημ/νία έκδοσης:` | `13-07-2026` | issue **date only** (no time) |
| Customer | `ΣΤΟΙΧΕΙΑ ΠΕΛΑΤΗ` → `Επωνυμία:` | `ΠΕΛΑΤΗΣ ΛΙΑΝΙΚΗΣ` | **Personal block. Never read** |
| Payment | `Τρόπος πληρωμής:` | `POS / e-POS` | payment method label (matches myDATA code 7 wording) |
| Items table | `ΚΩΔΙΚΟΣ` | `0205084` | merchant item code |
| | `ΠΕΡΙΓΡΑΦΗ` | `7DAYS MINI BA.RO150G` | description |
| | `ΜΜ` | `TEMAXIO`, `ΚΙΛΑ` | unit label (`TEMAXIO` is written in Latin letters) |
| | `ΠΟΣΟΤΗΤΑ` | `1,00`, `11,615` | quantity |
| | `ΤΙΜΗ ΜΟΝ.` | `1,40` | unit price (VAT-inclusive) |
| | `ΑΞΙΑ ΠΡΟ ΕΚΠΤ.` | `1,40` | value before discount = qty × unit price |
| | `ΕΚΠΤ.` | `0,04` | **line discount** |
| | `ΦΠΑ%` | `13%` | VAT rate |
| | `ΣΥΝΟΛΙΚΗ ΑΞΙΑ` | `1,36` | line gross after discount |
| Totals | `Αξία προ έκπτωσης` / `Έκπτωση` / `ΤΕΛΙΚΗ ΑΞΙΑ` | `79,28` / `3,80` / `75,48` | totals |
| | `Καθαρή Αξία` / `Φ.Π.Α` | `66,39` / `9,09` | net and VAT totals |
| VAT | `ΑΝΑΛΥΣΗ ΦΠΑ`: `ΦΠΑ%`, `ΚΑΘΑΡΟ ΠΟΣΟ ΑΝΑ ΦΠΑ`, `ΑΞΙΑ ΦΠΑ` | `13%`, `62,18`, `8,08` | VAT breakdown (6%, 13% and 24% seen) |
| Payment | `Τρόπος Πληρωμής` / `Ποσό Πληρωμής` | `POS / e-POS` / `75,48` | payments |
| Remarks | `UID:` / `M.AR.K:` | 40 hex / `4000143750…` | identity |
| | `AuthenticationCode:` | 40 hex | provider signature. **Discard** |
| | `Ημ/νία διαβίβασης:` | `13-07-2026 15:17:11` | time the document was transmitted to AADE |
| | `Πάροχος:`, `Url πάροχου:`, `Άδεια καταλληλότητας` | | raw only |

## 4. What is missing compared with Impact

| Missing | Consequence |
|---|---|
| myDATA document type code | Map the label to a code (`Απόδειξη Λιανικής Πώλησης` → `11.1`, …). An unknown label means `provider_format_changed` |
| VAT category codes | Derive the code from the rate (13% → `2`). Rates are unique in the official table except 4% (`6` or `10`), which stays without a code |
| Unit codes | Use the label: `TEMAXIO` → piece, `ΚΙΛΑ` → kg |
| Line net and VAT amounts | `Line.net` and `Line.vat` stay empty. Validation rules R4 and R6 skip these lines, and **R7 must compare only components that every line has** (needs a fix) |
| Time of issue | Only the transmission timestamp exists. Option: `issued_at` = date + transmission time when they fall on the same day, flagged as approximate. Otherwise midnight |
| Branch number | Store matched by address under the merchant (requirements §8.5 already allows it) |
| Legal entity name | The brand (`LIDL`) is shown. The VAT number still identifies the legal entity |
| A second view to cross-check | Replaced by arithmetic checks, which are exact on both samples: qty × price = value before discount; minus discount = line total; Σ lines = total; VAT breakdown = net/VAT totals |

## 5. Findings that affect the shared design

- **Real line discounts** exist and arrive per line, so `Line.discount`
  is filled. The effective price is the line total after discount.
  These are the first real data for requirements §10.3.
- **Bags are products here.** `ΣΑΚΟΥΛ.ΒΙΟΔ.25Μ1ΤΕΜ` (0,20 €) and
  `S.ΣΑΚΟΥΛΕΣ 60L 20Τ` (garbage bags) are purchases. The planned keyword
  rule `ΣΑΚΟΥΛ` → fee (requirements §9.1) would misclassify them. Fee
  classification must rely on fee amounts or line type codes, or on
  precise phrases (`ΠΕΡΙΒΑΛΛΟΝΤΙΚ ΤΕΛ`), never on the bare word.
- **Latin look-alike letters** appear in unit labels (`TEMAXIO`) and
  descriptions (`B.ΠΑΝΕΣ`, `XAΡ.ΚΟΥΖ.`). The §9.5 normalization covers
  this.

## 6. Personal and sensitive data

| Data | Action |
|---|---|
| Customer block (`ΣΤΟΙΧΕΙΑ ΠΕΛΑΤΗ`) | Never read. Sanitize in fixtures |
| `AuthenticationCode`, download token, myDATA QR token | Discard. Sanitize in fixtures |
| URL (doc UUID + hash token) | Bearer credential. Store once, never log |

## 7. Not-found behavior (observed 2026-11-14)

- With a wrong token, the **shell page still returns 200** and frames
  the document URL.
- The **document endpoint answers HTTP 418** with a ~300-byte page
  saying "Error 404: Page not found."
- The fetcher accepts 418 for this provider. The provider maps the page
  to `receipt_not_found`; any other 418 page means
  `provider_format_changed`.
