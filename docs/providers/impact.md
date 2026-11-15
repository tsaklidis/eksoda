# Impact e-receipt provider: observed response format

**Inspected:** 2026-11-13 and 2026-11-14, using the sample receipt URL
from the original requirements (Greek and English cultures, plus a
not-found page).
**Status:** Parser `impact/1` implemented in M2
(`backend/apps/receipts/providers/impact/`). It is tested against the
sanitized real sample in both cultures and synthetic variants, and
passes a live run against the real page. More real samples are needed
for the items in §7.

Impact SA is a certified Greek e-invoicing provider ("Πάροχος
Ηλεκτρονικής Τιμολόγησης"). It transmits every document to the AADE
**myDATA** platform. Impact's public receipt page therefore exposes the
same fields and code lists that every other certified provider sends to
AADE. This is why the canonical model in `requirements.md` is aligned
with myDATA rather than with Impact's HTML.

## 1. URL format

```
https://einvoice.impact.gr/p/{ISSUER_VAT}/{UID}/{ACCESS_GUID}
https://einvoice.impact.gr/p/EL094062259/FA8355776160C1AF53AC6A860C29C0BB1437029F/<32-hex access GUID, redacted>
```

| Segment | Example | Meaning |
|---|---|---|
| `ISSUER_VAT` | `EL094062259` | Issuer VAT number with `EL` country prefix |
| `UID` | 40 hex chars | AADE document UID (SHA-1 based); also printed on the page |
| `ACCESS_GUID` | 32 hex chars | Access token. A wrong value returns a "document not found" page |

The URL is effectively a **bearer credential**: anyone who has it can
view the full receipt without authentication. Treat it as sensitive.

The issuer VAT and UID can be read from the URL **before fetching**,
which enables pre-fetch duplicate detection.

## 2. Response characteristics

| Property | Observed |
|---|---|
| Rendering | Server-side rendered HTML (ASP.NET Blazor SSR). No JavaScript needed; no embedded JSON payload |
| Status | `200 OK`, no redirects |
| Content-Type | `text/html; charset=utf-8` |
| Size | ~100 KB (mostly CSS and markup) |
| Cookies | Sets `_culture`, antiforgery and session cookies |
| Robots | `<meta name="robots" content="noindex, nofollow">` (indexing only; not an access restriction) |
| Not found | **Also `200 OK`** with a small (~8 KB) page: "Document with UniqueId … and Guid …". You cannot rely on the HTTP status |
| Localization | Depends on the `_culture` cookie (details below) |
| Culture marker | `div.invoice` carries `data-culture="el"` or `data-culture="en"` |

**Localization details** (observed 2026-11-14):

| | Greek (`el`, default) | English (`en`) |
|---|---|---|
| Numbers (both views) | `0,622`, `1.234,56` | `0.622`, `1,234.56` |
| Commercial date | `07/11/2026 6:28 μ.μ.` (day/month) | `07/11/2026 6:28 PM` (**day/month**) |
| Tax-view date | `7/11/2026` (day/month) | `11/07/2026` (**month/day**) |
| Commercial labels | Greek | English |
| Tax-view labels | Greek | **Still Greek** |

**Consequences for the fetcher and parser**

- Never reuse cookies between fetches. Always fetch with an empty cookie
  jar so the page renders in the default Greek culture.
- Read the culture from `data-culture` and parse numbers strictly for
  it. Fail if the attribute is missing or unknown.
- Dates use a fixed order per (culture, view). The commercial and
  tax-view dates are cross-checked, which catches a silent format
  change whenever day ≠ month.
- Detect "not found" by the absence of the invoice container, not by
  HTTP status.
- **Use of the link:** the tax view itself labels the URL as the
  link with which the recipient can retrieve the document. Fetching it
  for the recipient's own records is therefore the intended use. No
  public terms of use for einvoicing.gr turned up in a search on
  2026-11-14. The fetcher stays polite: one request per import, a
  generic User-Agent, no cookies, and rate limits.

## 3. Page structure

The same document is rendered twice:

1. **Commercial view** ("Εμπορική Προβολή"): a human-readable receipt
   inside `div.invoice`. Each field is identified by a stable CSS class
   `field-<Name>`, with the value in a child `.value` element.
2. **Tax view** ("Φορολογική Προβολή"): the myDATA record inside
   `div.InvoicesDocDetailed`. It is a set of label/value tables (no field
   CSS classes), with myDATA code values.

The parser must read **both** views and cross-check them (section 6).

### 3.1 Commercial view fields

| Section / selector | Field class | Example | Canonical use |
|---|---|---|---|
| `#header` (1st address block) | `field-RegisteredName` | `METRO ΑΕΒΕ ΑΝΩΝΥΜΗ ΕΜΠΟΡΙΚΗ & …` | `merchant.legal_name` |
| | `field-Activities` | `ΛΙΑΝΙΚΟ ΕΜΠΟΡΙΟ ΣΕ ΜΗ ΕΞΕΙΔΙΚΕΥΜΕΝΑ …` | `merchant.activity_description` |
| | `field-Vat` | `EL094062259` | issuer VAT (cross-check with URL) |
| | `field-TaxOffice` | `ΚΕΦΟΔΕ ΑΤΤΙΚΗΣ` | `merchant.tax_office` |
| | `field-GeneralCommercialRegistryNumber` | `299401000` | `merchant.gemi_number` |
| | `field-RegistrationNumber` | `13836/01ΑΤ/Β/86/406` | raw only |
| | `field-Street`, `field-Number`, `field-City`, `field-Postal`, `field-Country` | `ΣΩΡΟΥ 1, ΜΕΤΑΜΟΡΦΩΣΗ 14451` | merchant head-office address |
| | `field-Phones`, `field-Emails`, `field-Url` | | raw only |
| `#header` (2nd address block) | `field-Street`, `field-City`, `field-Postal`, `field-Country` | `ΑΛΕΞΗ ΜΙΝΩΤΗ …, ΚΟΖΑΝΗ 50131` | **store (branch) address** |
| | `field-OtherInfo` | `ΑΜΠ 4925` | raw only |
| `.section-identity` | `field-InvoiceType` | `ΑΠΟΔΕΙΞΗ ΛΙΑΝΙΚΗΣ ΠΩΛΗΣΗΣ` | document type label |
| | `field-IssuerFormatedInvoiceSeriesNumber` | `7222-546093` | formatted receipt number |
| | `field-DateIssued` | `07/11/2026 6:28 μ.μ.` | issue time, local time (Europe/Athens), minute precision |
| `.section-counterparties` | `CounterParty` → `field-RegisteredName`, `field-Code` | `Πελάτης Λιανικής`, `72250…` | **Personal data (loyalty/customer code). Discard.** |
| `.section-details` table rows | `field-Code` | `127321` | merchant product code |
| | `field-Description1` | `ADORO LIGHT 10% ΦΡΑΤΖ. ΓΕΡΜΑΝΙΑΣ(Τ.ΚΙΛΟΥ` | original description |
| | `field-Quantity` | `0,622` | quantity |
| | `field-MeasurementUnit` | `ΚΙΛΑ` / `ΤΕΜΑΧ` | unit label |
| | `field-UnitPrice` | `7,21` | **VAT-inclusive** unit price |
| | `field-NetTotal` | `3,96` | line net amount |
| | `field-VatCategory` | `13` | VAT rate in percent (not the myDATA code) |
| | `field-VATTotal` | `0,52` | line VAT amount |
| | `field-Total` | `4,48` | line gross amount |
| `.section-taxes` | `field-Percentage`, `field-UnderlyingValue`, `field-VatAmount` | `13,00%`, `8,10`, `1,05` | VAT breakdown per rate |
| `.section-paymentanalysis` | `field-PaymentMethodType` | `VISA` | payment method label |
| | `field-Amount` | `9,15` | payment amount |
| | `field-TransactionId` | `1166…` | **Personal/payment data. Discard.** |
| `.section-summaries` | `field-CurrencyCode`, `field-TotalNetAmount`, `field-TotalVATAmount`, `field-TotalGrossValue` | `EUR`, `8,10`, `1,05`, `9,15` | receipt totals |
| `.section-miscellaneous` | `field-MoreInformation1` | legal footer text | raw only |
| `.section-certification` | `field-Mark` | `400015963897868` | **AADE MARK** |
| | `field-Uid` | `FA8355…029F` | AADE UID (cross-check with URL) |
| | `field-Authentication Code` | 40 hex | provider signature. Discard |
| | `field-ServiceSupplier` | `Impact SA …` | raw only |

The unit price is VAT-inclusive:
`0.622 × 7.21 = 4.4846 → 4.48` (the gross amount), and
`0.126 × 14.60 = 1.8396 → 1.84`.

### 3.2 Tax view (myDATA) fields

Labels are shown in the default (Greek) culture.

| Group | Label | Example | Canonical use |
|---|---|---|---|
| General | Σειρά Παραστατικού | `7222` | `series` |
| | ΑΑ Παραστατικού | `546093` | `number` |
| | Ημερομηνία Έκδοσης | `7/11/2026` | issue date (date only) |
| | Είδος Παραστατικού | `11.1` | **myDATA document type** |
| | Νόμισμα | `EUR` | currency |
| | Ένδειξη Αυτοτιμολόγησης | `Όχι` | self-billing flag (raw) |
| Issuer | ΑΦΜ / Κωδ. Χώρας | `094062259` / `GR` | merchant identity |
| | Αρ. Εγκατάστασης | `264` | **branch (installation) number → store identity** |
| Summary | Σύνολο Καθαρής Αξίας | `8,10` | net total |
| | Σύνολο ΦΠΑ | `1,05` | VAT total |
| | Σύνολο Παρ. Φόρων | `0,00` | withheld taxes total |
| | Σύνολο Τελών | `0,00` | fees total |
| | Σύνολο Ψηφιακού Τέλους συναλλαγής | `0,00` | digital transaction fee total |
| | Σύνολο Λοιπών Φόρων | `0,00` | other taxes total |
| | Σύνολο Κρατήσεων | `0,00` | deductions total |
| | Συνολική Αξία | `9,15` | gross total |
| Payments | Τύπος Πληρωμής | `7` | myDATA payment method code (7 = POS / e-POS) |
| | Αναλογούν Ποσό / Φιλοδώρημα | `9,15` / `0,00` | payment amount / tip |
| | Μοναδική Ταυτότητα Πληρωμής, ID Τερματικού POS, Υπογραφή | | **Discard** |
| Identifiers | Μοναδικός Αριθμός Καταχώρησης Παραστατικού | `400015963897868` | MARK |
| | Αναγνωριστικό Παραστατικού | 40 hex | UID |
| | Url με το οποίο ο λήπτης … | the receipt URL | cross-check with the submitted URL |
| | Αδυναμία Επικοινωνίας Παρόχου … | `0` | transmission-failure flag (MARK may be missing when set) |
| | Μοναδικός Αριθμός Καταχώρησης Ακυρωτικού | `0` | **cancellation MARK**. Non-zero means the receipt was cancelled |
| Lines (one table per line) | ΑΑ Γραμμής | `1` | source line number |
| | Είδος Γραμμής | `0` | myDATA line type code (0 = ordinary line in the sample) |
| | Κωδικός Είδους / Περιγραφή Είδους | | code / description |
| | Ποσότητα | `0,622` | quantity |
| | Είδος Ποσότητας | `2` / `1` | **myDATA measurement unit code** (1 = pieces, 2 = kg) |
| | Επισήμανση | `0` | line annotation code (raw) |
| | Καθαρή Αξία / Ποσό ΦΠΑ | `3,96` / `0,52` | net / VAT |
| | Κατηγορία ΦΠΑ | `2` | **myDATA VAT category code** (2 = 13%) |
| | Κατηγορία Αιτίας Εξαίρεσης ΦΠΑ | `0` | VAT exemption reason (raw) |
| | Ποσό Παρ. Φόρου, Ποσό Τελών, Ψηφιακό Τέλος, Φόρος Διαμονής, Ποσό Κρατήσεων (+ categories) | `0,00` | line-level withholding / fees / other taxes / deductions |
| | Σχόλια Γραμμής | empty | line comments (raw) |

There is also an "Εγγραφή στο MyData" link to
`mydatapi.aade.gr/myDATA/TimologioQR/QRInfo?q=…`. It is meant for
business recipients classifying expenses. It is not used.

## 4. Sample receipt summary

| | |
|---|---|
| Merchant | METRO ΑΕΒΕ, VAT 094062259 (one legal entity; can operate more than one retail brand) |
| Store | Branch 264, Κοζάνη |
| Document | 11.1 Retail sales receipt, `7222-546093`, 2026-11-07 18:28 Europe/Athens |
| Lines | 5 (2 weighted in kg, 3 pieces), all 13% VAT |
| Totals | net 8.10 + VAT 1.05 = gross 9.15 EUR (lines sum exactly) |
| Payment | myDATA code 7 (card, "VISA"), 9.15 |

Line descriptions appear to be capped at **40 characters**. For example,
`ADORO LIGHT 10% ΦΡΑΤΖ. ΓΕΡΜΑΝΙΑΣ(Τ.ΚΙΛΟΥ` is cut off mid-word
("τιμή κιλού"). Descriptions mix Latin and Greek letters. Package sizes
appear inline (`1L`, `1,5% 1L`) and can be ambiguous
(`27/250ML`). **No barcodes** are present. The merchant product code is
the strongest product identifier this provider offers.

## 5. Personal and sensitive data in the response

| Data | Action |
|---|---|
| Customer/loyalty code (`CounterParty` → `Code`) | Discard at parse time. Never persist |
| Card transaction ID, payment unique ID, POS terminal ID, payment signature | Discard |
| Provider authentication string / signatures | Discard |
| Receipt URL (contains access GUID) | Store once; never log in full |
| QR code SVG and the `title` of its container | They encode the receipt URL. Removed from fixtures |
| myDATA QR link (`mydatapi.aade.gr/...QRInfo?q=…`) | The token is replaced in fixtures |
| Merchant data (VAT, address, phone) | Public business data. Keep |

**Traps found while implementing:**

- The customer code shares the `field-Code` class with the line item
  codes. Line fields must be read inside `.section-details`.
- Commercial summary rows are also two-cell `label | value` table rows,
  and "Συνολική Αξία" appears in both views. Tax-view rows must be read
  inside `.InvoicesDocDetailed`.

## 6. Parsing strategy

1. **Detect the page kind.** A page with `div.invoice` and
   `div.InvoicesDocDetailed` is a receipt. A page without them that
   contains the "Document with UniqueId" message is *not found*.
   Anything else is an *unexpected format*.
2. **Detect the culture** from `div.invoice[data-culture]` and choose
   the strict number and date parsers for it.
3. **Extract the commercial view** using `field-*` classes.
4. **Extract the tax view** by mapping known labels (Greek in every
   culture) to field keys:
   - Unknown labels go into `unknown_fields`. They are counted as format
     drift but do not cause a failure. Values under unknown *payment*
     labels are not kept, because they may be personal.
   - Rows in a buyer `Party` table and labels on the drop list are never
     read.
5. **Cross-check the two views.** The line count must match. Each line's
   net, VAT and gross must match. The totals must match. The UID and
   issuer VAT must match the URL. Any disagreement means
   `inconsistent_source` and the import fails visibly.
6. **Required fields:** issuer VAT, UID, document type, issue date, gross
   total, at least one line, and net, VAT and gross on every line. The
   MARK is also required unless the transmission-failure flag is set.
   A missing required field means `provider_format_changed`.
7. **Use the tax view** for identifiers, codes and amounts. Use the
   **commercial view** for unit price, unit label, VAT %, addresses,
   names and time of day.

## 7. Unknowns (collect more sample receipts)

None of these appear in the single real sample. Synthetic variants built
from the sample cover credit notes, cancellations, cash, missing MARK,
missing optional fields, a 24% fee line and a negative discount line
(`backend/tests/receipts/providers/test_impact_variants.py`). Replace
them with real sanitized receipts (`receipt-fixture` skill) as they
become available:

- Discount, coupon or promotion lines (negative lines, line type codes).
- Carrier-bag environmental fee lines and other fee lines.
- Deposits or returns.
- Credit notes (myDATA 11.4) and cancelled receipts (non-zero
  cancellation MARK).
- Several VAT rates on one receipt (6%, 13%, 24%).
- Cash payments and split payments.
- Non-grocery merchants (pharmacy, restaurant, fuel, clothing).
- Receipts with many lines (check whether lines are paginated).
- Missing MARK (provider transmission failure).
- Variants of the URL format, if any exist.
