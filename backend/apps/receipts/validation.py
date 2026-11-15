"""Provider-neutral receipt validation (requirements §10.2, TD §11).

Rules R1–R3 (identity, view agreement, required fields) are fatal and enforced by
the provider parsers. The rules here only produce warnings: source values are
never changed to make a rule pass. Rules adapt to the receipt's ``coverage``
(e.g. summary-only sources have no lines; some sources have no line VAT amounts).

R4  line composition          net + VAT + fees + … − withheld − deductions = gross
R5  unit price                qty × unit price = gross before discount (or gross)
R6  VAT rate                  net × rate = VAT
R7  totals vs lines           Σ line values = receipt totals (only fully provided values)
R8  receipt composition       net + VAT + fees + … − withheld − deductions = gross
R9  VAT breakdown             Σ breakdown net/VAT = net/VAT totals
R10 payments                  Σ payments = gross
R11 MARK                      present for myDATA-registered documents
R12 currency                  EUR
R13 line discount             gross before discount − discount = gross
R14 VAT breakdown rate        breakdown net × rate = breakdown VAT
R15 document kind             the document type is recognized
R16 total discount            total before discount − discount = gross
+   provider notices          conditions the provider detected (e.g. signature mismatch)
"""

from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal

from apps.receipts.canonical import CanonicalReceipt, Line
from apps.receipts.mydata import DocumentKind

LINE_TOLERANCE = Decimal("0.01")
TOTAL_TOLERANCE = Decimal("0.02")
CENT = Decimal("0.01")
EXPECTED_CURRENCY = "EUR"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    line_number: int | None = None
    expected: str | None = None
    actual: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _z(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal("0")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _off(expected: Decimal, actual: Decimal, tolerance: Decimal) -> bool:
    return abs(expected - actual) > tolerance


def _issue(code, message, line=None, expected=None, actual=None) -> ValidationIssue:
    return ValidationIssue(
        code,
        message,
        line,
        None if expected is None else str(expected),
        None if actual is None else str(actual),
    )


def validate(receipt: CanonicalReceipt) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for line in receipt.lines:
        issues += _line_composition(line)
        issues += _unit_price(line)
        issues += _vat_rate(line)
        issues += _line_discount(line)
    issues += _totals_match_lines(receipt)
    issues += _receipt_composition(receipt)
    issues += _vat_breakdown(receipt)
    issues += _vat_breakdown_rates(receipt)
    issues += _payments(receipt)
    issues += _mark(receipt)
    issues += _currency(receipt)
    issues += _document_kind(receipt)
    issues += _total_discount(receipt)
    issues += [_issue(notice.code, notice.message) for notice in receipt.notices]
    return issues


def line_expected_gross(line: Line) -> Decimal:
    return (
        _z(line.net)
        + _z(line.vat)
        + _z(line.fees)
        + _z(line.other_taxes)
        + _z(line.stamp_duty)
        + _z(line.digital_fee)
        - _z(line.withheld)
        - _z(line.deductions)
    )


def _line_composition(line: Line) -> list[ValidationIssue]:  # R4
    if line.net is None or line.vat is None:
        return []
    expected = line_expected_gross(line)
    if _off(expected, line.gross, LINE_TOLERANCE):
        return [
            _issue(
                "line_amount_mismatch",
                "Line amounts do not add up to the line total.",
                line.line_number,
                expected,
                line.gross,
            )
        ]
    return []


def _unit_price(line: Line) -> list[ValidationIssue]:  # R5
    if line.unit_price is None or line.quantity is None:
        return []
    if line.gross_before_discount is not None:
        target = line.gross_before_discount
    elif line.discount is not None:
        return []  # discounted, and the pre-discount value is unknown
    else:
        target = {"gross": line.gross, "net": line.net}.get(line.unit_price_basis)
    if target is None:
        return []
    expected = _money(line.quantity * line.unit_price)
    if _off(expected, target, LINE_TOLERANCE):
        return [
            _issue(
                "unit_price_mismatch",
                "Quantity × unit price does not match the line amount.",
                line.line_number,
                expected,
                target,
            )
        ]
    return []


def _vat_rate(line: Line) -> list[ValidationIssue]:  # R6
    if line.vat_rate is None or line.net is None or line.vat is None:
        return []
    expected = _money(line.net * line.vat_rate / 100)
    if _off(expected, line.vat, LINE_TOLERANCE):
        return [
            _issue(
                "vat_rate_mismatch",
                "The VAT amount does not match the VAT rate.",
                line.line_number,
                expected,
                line.vat,
            )
        ]
    return []


def _line_discount(line: Line) -> list[ValidationIssue]:  # R13
    if line.gross_before_discount is None or line.discount is None:
        return []
    expected = line.gross_before_discount - line.discount
    if _off(expected, line.gross, LINE_TOLERANCE):
        return [
            _issue(
                "discount_mismatch",
                "The value before discount minus the discount does not match the line total.",
                line.line_number,
                expected,
                line.gross,
            )
        ]
    return []


def _totals_match_lines(receipt: CanonicalReceipt) -> list[ValidationIssue]:  # R7
    if not receipt.lines:
        return []
    issues = []
    for name in ("net", "vat", "gross"):
        values = [getattr(line, name) for line in receipt.lines]
        total = getattr(receipt.totals, name)
        if total is None or any(value is None for value in values):
            continue  # only compare values every line provides
        line_sum = sum(values, Decimal("0"))
        if _off(line_sum, total, TOTAL_TOLERANCE):
            issues.append(
                _issue(
                    "total_mismatch",
                    f"The receipt {name} total differs from the sum of its lines.",
                    None,
                    line_sum,
                    total,
                )
            )
    return issues


def _receipt_composition(receipt: CanonicalReceipt) -> list[ValidationIssue]:  # R8
    t = receipt.totals
    if t.net is None or t.vat is None:
        return []
    expected = (
        t.net
        + t.vat
        + _z(t.fees)
        + _z(t.other_taxes)
        + _z(t.stamp_duty)
        + _z(t.digital_fee)
        - _z(t.withheld)
        - _z(t.deductions)
    )
    if _off(expected, t.gross, LINE_TOLERANCE):
        return [
            _issue(
                "receipt_amount_mismatch",
                "The receipt totals do not add up to the gross total.",
                None,
                expected,
                t.gross,
            )
        ]
    return []


def _vat_breakdown(receipt: CanonicalReceipt) -> list[ValidationIssue]:  # R9
    if not receipt.vat_breakdown:
        return []
    issues = []
    for name in ("net", "vat"):
        total = getattr(receipt.totals, name)
        if total is None:
            continue
        breakdown = sum((getattr(entry, name) for entry in receipt.vat_breakdown), Decimal("0"))
        if _off(breakdown, total, LINE_TOLERANCE):
            issues.append(
                _issue(
                    "vat_breakdown_mismatch",
                    f"The VAT breakdown does not add up to the {name} total.",
                    None,
                    breakdown,
                    total,
                )
            )
    return issues


def _vat_breakdown_rates(receipt: CanonicalReceipt) -> list[ValidationIssue]:  # R14
    issues = []
    for entry in receipt.vat_breakdown:
        if entry.rate is None:
            continue
        expected = _money(entry.net * entry.rate / 100)
        if _off(expected, entry.vat, LINE_TOLERANCE):
            issues.append(
                _issue(
                    "vat_breakdown_rate_mismatch",
                    f"The VAT for the {entry.rate}% rate does not match its net amount.",
                    None,
                    expected,
                    entry.vat,
                )
            )
    return issues


def _payments(receipt: CanonicalReceipt) -> list[ValidationIssue]:  # R10
    if not receipt.payments:
        return []
    paid = sum((payment.amount for payment in receipt.payments), Decimal("0"))
    if _off(paid, receipt.totals.gross, LINE_TOLERANCE):
        return [
            _issue(
                "payment_mismatch",
                "The payments do not add up to the gross total.",
                None,
                receipt.totals.gross,
                paid,
            )
        ]
    return []


def _mark(receipt: CanonicalReceipt) -> list[ValidationIssue]:  # R11
    identity = receipt.identity
    if (
        receipt.coverage.mydata_registered
        and identity.mark is None
        and not identity.transmission_failure
    ):
        return [_issue("mark_missing", "The receipt has no AADE registration number.")]
    return []


def _currency(receipt: CanonicalReceipt) -> list[ValidationIssue]:  # R12
    if receipt.document.currency != EXPECTED_CURRENCY:
        return [
            _issue(
                "non_eur_currency",
                "The receipt is not in EUR.",
                None,
                EXPECTED_CURRENCY,
                receipt.document.currency,
            )
        ]
    return []


def _document_kind(receipt: CanonicalReceipt) -> list[ValidationIssue]:  # R15
    if receipt.document.kind is DocumentKind.OTHER:
        return [
            _issue(
                "unknown_document_type",
                "The document type is not recognized; check whether it is a sale or a refund.",
                None,
                None,
                receipt.document.type_label or receipt.document.type_code,
            )
        ]
    return []


def _total_discount(receipt: CanonicalReceipt) -> list[ValidationIssue]:  # R16
    t = receipt.totals
    if t.gross_before_discount is None or t.discount is None:
        return []
    expected = t.gross_before_discount - t.discount
    if _off(expected, t.gross, LINE_TOLERANCE):
        return [
            _issue(
                "total_discount_mismatch",
                "The total before discount minus the discount does not match the gross total.",
                None,
                expected,
                t.gross,
            )
        ]
    return []
