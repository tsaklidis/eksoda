"""Provider-independent receipt representation (pure Python, requirements §7.2, TD §9.1).

Provider adapters produce a CanonicalReceipt; the core only consumes this type.
Amounts are Decimal and always keep the values printed by the source. Sources
differ in what they provide, so every receipt states its ``coverage``.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from apps.receipts.mydata import DocumentKind, PaymentMethod, Unit

PriceBasis = Literal["gross", "net", "unknown"]
IssueTime = Literal["exact", "approximate", "date_only"]


@dataclass(frozen=True, slots=True)
class Coverage:
    """What the source provides. Validation and analytics adapt to it."""

    line_items: bool = True  # purchased items are listed
    line_tax_amounts: bool = True  # lines carry their own net and VAT amounts
    official_codes: bool = True  # type/VAT/unit codes are myDATA codes, not derived from labels
    mydata_registered: bool = True  # an AADE MARK is expected
    issue_time: IssueTime = "exact"  # "approximate": e.g. transmission time on the same day
    cross_checked: bool = True  # two independent renderings were compared


@dataclass(frozen=True, slots=True)
class Notice:
    """A condition the provider detected that the user should see (becomes a warning)."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class Address:
    street: str | None = None
    number: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country: str | None = None


@dataclass(frozen=True, slots=True)
class Party:
    country_code: str
    vat_number: str
    legal_name: str
    activity: str | None = None
    tax_office: str | None = None
    gemi_number: str | None = None
    address: Address | None = None


@dataclass(frozen=True, slots=True)
class Branch:
    number: str | None = None
    address: Address | None = None


@dataclass(frozen=True, slots=True)
class Document:
    kind: DocumentKind
    issued_at: datetime
    issued_date: date
    currency: str
    type_code: str | None = None  # myDATA type; None when the source gives only a label
    type_label: str | None = None
    series: str | None = None
    number: str | None = None
    formatted_number: str | None = None


@dataclass(frozen=True, slots=True)
class Identity:
    uid: str | None = None
    mark: str | None = None
    cancellation_mark: str | None = None
    transmission_failure: bool = False
    source_key: str | None = None  # natural key for sources without MARK/UID (e.g. cash registers)


@dataclass(frozen=True, slots=True)
class Totals:
    gross: Decimal
    net: Decimal | None = None
    vat: Decimal | None = None
    withheld: Decimal | None = None
    fees: Decimal | None = None
    other_taxes: Decimal | None = None
    stamp_duty: Decimal | None = None
    digital_fee: Decimal | None = None
    deductions: Decimal | None = None
    gross_before_discount: Decimal | None = None
    discount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class VatEntry:
    net: Decimal
    vat: Decimal
    rate: Decimal | None = None
    category_code: str | None = None


@dataclass(frozen=True, slots=True)
class Payment:
    amount: Decimal
    method: PaymentMethod | None = None
    method_code: str | None = None  # myDATA code when the source shows it
    method_label: str | None = None
    tip: Decimal = Decimal("0")
    derived: bool = False  # inferred (e.g. cash = total − card), not printed by the source


@dataclass(frozen=True, slots=True)
class Line:
    line_number: int
    description: str
    gross: Decimal  # amount paid for the line, after any line discount
    quantity: Decimal | None = None
    unit: Unit | None = None
    unit_code: str | None = None  # myDATA code when the source shows it
    unit_label: str | None = None
    unit_price: Decimal | None = None
    unit_price_basis: PriceBasis = "unknown"
    gross_before_discount: Decimal | None = None
    discount: Decimal | None = None
    net: Decimal | None = None
    vat_category_code: str | None = None
    vat_rate: Decimal | None = None
    vat: Decimal | None = None
    withheld: Decimal | None = None
    fees: Decimal | None = None
    other_taxes: Decimal | None = None
    stamp_duty: Decimal | None = None
    digital_fee: Decimal | None = None
    deductions: Decimal | None = None
    merchant_product_code: str | None = None
    barcode: str | None = None
    line_type_code: str | None = None
    annotation_code: str | None = None
    vat_exemption_code: str | None = None
    raw: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CanonicalReceipt:
    provider_code: str
    parser_version: str
    culture: str
    source_url: str
    issuer: Party
    document: Document
    identity: Identity
    totals: Totals
    lines: tuple[Line, ...]  # empty for summary-only sources (coverage.line_items False)
    coverage: Coverage = field(default_factory=Coverage)
    branch: Branch | None = None
    vat_breakdown: tuple[VatEntry, ...] = ()
    payments: tuple[Payment, ...] = ()
    notices: tuple[Notice, ...] = ()
    provider_payload: Mapping[str, Any] = field(default_factory=dict)
    unknown_fields: Mapping[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        """JSON-compatible dict: Decimal → str, dates → ISO 8601, tuples → lists."""
        return to_jsonable(self)


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    return value
