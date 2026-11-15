"""AADE myDATA code lists (pure Python, TD §9.2).

Every Greek e-receipt provider reports the same myDATA codes, so these tables are
provider-neutral. Source: AADE "myDATA REST API Documentation" v1.0.9 (official,
English, 2024-10), appendix 8.1, 8.2, 8.12 and 8.13 (checked 2026-11-14).

Unknown codes never raise: they map to OTHER / None and the raw code is kept.
"""

from decimal import Decimal
from enum import StrEnum


class DocumentKind(StrEnum):
    SALE = "sale"
    CREDIT_NOTE = "credit_note"
    OTHER = "other"


class Unit(StrEnum):
    PIECE = "piece"
    KG = "kg"
    L = "l"
    OTHER = "other"


class PaymentMethod(StrEnum):
    CARD = "card"
    CASH = "cash"
    BANK = "bank"
    OTHER = "other"
    UNKNOWN = "unknown"


# 8.1 Invoice type (subset relevant to household purchases).
DOCUMENT_TYPES: dict[str, str] = {
    "1.1": "Sales Invoice",
    "1.2": "Sales Invoice/Intra-community Supplies",
    "1.3": "Sales Invoice/Third Country Supplies",
    "1.4": "Sales Invoice/Sale on Behalf of Third Parties",
    "1.5": "Sales Invoice/Clearance of Sales on Behalf of Third Parties",
    "1.6": "Sales Invoice/Supplemental Accounting Source Document",
    "2.1": "Service Rendered Invoice",
    "2.2": "Intra-community Service Rendered Invoice",
    "2.3": "Third Country Service Rendered Invoice",
    "2.4": "Service Rendered Invoice/Supplemental Accounting Source Document",
    "5.1": "Credit Invoice/Associated",
    "5.2": "Credit Invoice/Non-Associated",
    "11.1": "Retail Sales Receipt",
    "11.2": "Service Rendered Receipt",
    "11.3": "Simplified Invoice",
    "11.4": "Retail Sales Credit Note",
    "11.5": "Retail Sales Receipt on Behalf of Third Parties",
}
CREDIT_NOTE_TYPES = frozenset({"5.1", "5.2", "11.4"})
SALE_TYPES = frozenset(DOCUMENT_TYPES) - CREDIT_NOTE_TYPES

# 8.2 VAT category → rate in percent (None: records without VAT, e.g. payroll).
VAT_RATES: dict[str, Decimal | None] = {
    "1": Decimal("24"),
    "2": Decimal("13"),
    "3": Decimal("6"),
    "4": Decimal("17"),
    "5": Decimal("9"),
    "6": Decimal("4"),
    "7": Decimal("0"),
    "8": None,
    "9": Decimal("3"),  # Article 31, Law 5057/2023
    "10": Decimal("4"),  # Article 31, Law 5057/2023
}

# 8.13 Unit of measurement.
MEASUREMENT_UNITS: dict[str, Unit] = {"1": Unit.PIECE, "2": Unit.KG, "3": Unit.L}

# 8.12 Payment methods.
PAYMENT_METHODS: dict[str, PaymentMethod] = {
    "1": PaymentMethod.BANK,  # domestic payments account number
    "2": PaymentMethod.BANK,  # foreign payments account number
    "3": PaymentMethod.CASH,
    "4": PaymentMethod.OTHER,  # check
    "5": PaymentMethod.OTHER,  # on credit
    "6": PaymentMethod.BANK,  # web banking
    "7": PaymentMethod.CARD,  # POS / e-POS
    "8": PaymentMethod.BANK,  # direct payments IRIS
}

# Line type (8.16) and remark (8.15) codes are only stored as printed (Line.line_type_code,
# Line.annotation_code); nothing interprets them.


def normalize_code(code: str | None) -> str | None:
    """Trim a code; blank means absent. Integer codes lose leading zeros ("07" → "7")."""
    if code is None:
        return None
    value = code.strip()
    if not value:
        return None
    return str(int(value)) if value.isdigit() else value


def is_absent(code: str | None) -> bool:
    """Optional myDATA integer codes are rendered as "0" when not set."""
    return normalize_code(code) in (None, "0")


def document_kind(type_code: str | None) -> DocumentKind:
    code = (type_code or "").strip()
    if code in CREDIT_NOTE_TYPES:
        return DocumentKind.CREDIT_NOTE
    if code in SALE_TYPES:
        return DocumentKind.SALE
    return DocumentKind.OTHER


def is_known_vat_category(code: str | None) -> bool:
    return normalize_code(code) in VAT_RATES


def vat_rate(category_code: str | None) -> Decimal | None:
    return VAT_RATES.get(normalize_code(category_code) or "")


def measurement_unit(code: str | None) -> Unit | None:
    normalized = normalize_code(code)
    if normalized is None:
        return None
    return MEASUREMENT_UNITS.get(normalized, Unit.OTHER)


def payment_method(code: str | None) -> PaymentMethod:
    normalized = normalize_code(code)
    if normalized is None:
        return PaymentMethod.UNKNOWN
    return PAYMENT_METHODS.get(normalized, PaymentMethod.OTHER)
