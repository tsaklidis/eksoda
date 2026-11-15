# AADE public check pages: observed formats

**Inspected:** 2026-11-14. One cash-register receipt check page (from
the owner) and the myDATA document page linked from both e-receipt
providers.
**Status:** The cash-register page is implemented in M2b
(`backend/apps/receipts/providers/aade_fhm/`, layout `aade_fhm/1`), with fixtures for a
receipt, a signature mismatch and a not-transmitted receipt. The myDATA summary page
is documented only.

AADE runs two public pages that confirm a receipt.

## 1. Cash-register (ΦΗΜ) receipt check: `www1.aade.gr/tameiakes`

Paper receipts printed by electronic cash registers (ΦΗΜ) carry a QR
code that links here. Many smaller shops still issue these instead of
e-receipts. The sample is from 2024, so old receipts can be imported
too.

### URL

```
https://www1.aade.gr/tameiakes/myweb/q1.php?SIG=<signature string, redacted>
```

The observed `SIG` decomposition, which must be confirmed with more
samples:

1. Cash-register id (11 characters, e.g. `FGG18025203`).
2. Receipt sequence number (8 digits).
3. A 30-hex signature.
4. `yyMMddHHmm`.
5. The total amount (`34.93`).

The page repeats every value, so the parser does not need to decode
`SIG`. The cash-register id plus the sequence number (plus the date)
form a stable identity for duplicate detection.

### Response

About 9 KB of server-rendered Greek HTML with a label/value table
(`table.info`). Numbers use a **decimal point** (`34.93`, `€ 24.87`).
The date and time are ISO-like (`2024-05-17 09:51`). The page sets
cookies, which are not needed. It can contain status text such as
"this cash register is not active today", which does not affect the
receipt data.

| Label | Example | Canonical use |
|---|---|---|
| Συνολική αξία | `€ 34.93` | gross total |
| Ποσό πληρωμής με κάρτα | `€ 0.00` | card amount. The remainder is presumably cash |
| Ημερομηνία, ώρα | `2024-05-17 09:51` | `issued_at` (Europe/Athens) |
| Ημερήσιος α/α | `35` | raw |
| ΦΗΜ | `FGG18025203` | cash-register id (identity) |
| ΑΦΜ εκδότη | `094025817` | issuer VAT |
| Επωνυμία | `ΑΛΦΑ ΒΗΤΑ ΒΑΣΙΛΟΠΟΥΛΟΣ ΜΟΝΟΠΡΟ` | merchant name (truncated) |
| Διεύθυνση | `ΘΗΒΩΝ ΚΑΙ ΙΔΟΜΕΝΕΟΥΣ … TK:13121 ΙΛΙΟΝ` | address. The cash register's location, so presumably the store |
| Αριθμός Ζ / Προοδευτικός α/α | `1660` / `686373` | raw / identity |
| Είδος παραστατικού | `ΑΠΟΔΕΙΞΗ ΠΑΡΟΧΗΣ ΥΠΗΡΕΣΙΩΝ - ΑΠΟΔΕΙΞΗ ΛΙΑΝΙΚΗΣ ΠΩΛΗΣΗΣ` | document type label |
| Σειρά / Αριθμός παραστατικού | `1072` / `27935` | series / number |
| ΑΦΜ λήπτη (σε τιμολόγιο) | empty | **Buyer VAT (personal). Never read** |
| Καθαρή αξία Α–Ε / ΦΠΑ Α–Δ | `Β: 24.87 / 3.23`, `Γ: 5.51 / 1.32` | VAT breakdown by cash-register VAT category |
| Νόμισμα συναλλαγής | `0# Euro Member Countries` | currency |
| Κωδικός / Λίτρα καυσίμου | `#` / `0` | fuel stations only (raw) |

**Cash-register VAT categories:** in the sample, Β = 13% (3.23 / 24.87)
and Γ = 24% (1.32 / 5.51). The usual mapping is Α = 6%, Β = 13%,
Γ = 24%, Δ = 36% and Ε = exempt. **Verify it before relying on it.** The
parser should also check each category's rate arithmetically.

### What it means for the product

- **No line items and no MARK.** These receipts give merchant, store,
  date and time, totals, VAT breakdown and payment split, but no
  products. They count fully in spending analytics (by merchant and
  monthly; by category they go to "Unallocated", which requirements §13
  already defines) and add nothing to price history.
- This needs a **product decision (proposed D20):** accept receipts
  without lines from summary-only sources. Today the canonical model
  and the Impact parser require at least one line.

## 2. myDATA document page: `mydatapi.aade.gr/myDATA/TimologioQR/QRInfo?q=…`

Both Impact and Entersoft pages link here (Impact's button is "Εγγραφή
στο MyData", Entersoft's is "Παραστατικό (ΑΑΔΕ)"). The `q` token is
opaque.

- About 27 KB HTML. Values sit in read-only `input` fields: document
  type label (`ΑΛΠ (Απόδειξη Λιανικής Πώλησης)`), MARK, series, number,
  issue date (`13/07/2026`), gross, net, VAT and issuer VAT.
  Merchant name, activity and address are **empty**.
- **Summary only,** with no lines. It is not a substitute for the
  provider page. It could later serve as an independent check of totals
  and MARK, or as a summary-only fallback for e-receipts from providers
  that are not supported yet. Not planned.

## 3. Cash-register page edge cases (observed 2026-11-14)

| Case | Page | Result |
|---|---|---|
| Unknown or not yet transmitted receipt | HTTP 200. Header echo, then "Η απόδειξη δεν έχει διαβιβαστεί στην ΑΑΔΕ" plus a cash-register info table. The page notes that fuel receipts are transmitted at the end of the day | `receipt_not_found` (retried on the long schedule) |
| QR signature differs from AADE's record | HTTP 200. Full record plus the alert "Διαφορά στην ψηφιακή υπογραφή!" | Imported from AADE's record, with a `signature_mismatch` warning |
| QR amount differs from the record | The header echo ("Συνολικού ποσού …") ≠ "Συνολική αξία" | `amount_mismatch` warning |
| Cash register inactive today | Alert "δεν είναι ενεργή ή είναι αδήλωτη" | Kept in the payload; not a warning |
