"""Spending analytics (requirements §13, TD §15). Read-only.

- Included receipts: active, not excluded by the user, in the household's currency,
  issued within the period (household timezone).
- Spending: Σ gross total, negative for credit notes.
- Everything is aggregated in the database; Python only combines a handful of
  aggregated rows.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.db.models import (
    Case,
    Count,
    DecimalField,
    F,
    Q,
    QuerySet,
    Sum,
    UUIDField,
    Value,
    When,
)
from django.db.models.functions import Coalesce, TruncMonth

from apps.analytics.periods import Period, add_months
from apps.households.models import Household
from apps.products.models import ProductCategory
from apps.products.prices import PRICE_HISTORY
from apps.receipts.models import Receipt, ReceiptItem

_MONEY = DecimalField(max_digits=14, decimal_places=2)
_ZERO = Decimal("0.00")
_CENT = Decimal("0.01")
CREDIT_NOTE = Receipt.Kind.CREDIT_NOTE
SALE = Receipt.Kind.SALE

SIGNED_GROSS = Case(
    When(document_kind=CREDIT_NOTE, then=-F("gross_total")),
    default=F("gross_total"),
    output_field=_MONEY,
)
SIGNED_LINE_GROSS = Case(
    When(receipt__document_kind=CREDIT_NOTE, then=-F("gross_amount")),
    default=F("gross_amount"),
    output_field=_MONEY,
)

# Category buckets that are not categories (requirements §13).
UNCATEGORIZED = "uncategorized"
DISCOUNTS = "discounts"
FEES = "fees_deposits"
OTHER_ADJUSTMENTS = "other_adjustments"
UNALLOCATED = "unallocated"
BUCKET_NAMES = {
    UNCATEGORIZED: "Uncategorized",
    DISCOUNTS: "Discounts",
    FEES: "Fees and deposits",
    OTHER_ADJUSTMENTS: "Other adjustments",
    UNALLOCATED: "Unallocated",
}
_LINE_BUCKETS = {
    ReceiptItem.LineType.DISCOUNT: DISCOUNTS,
    ReceiptItem.LineType.FEE: FEES,
    ReceiptItem.LineType.OTHER: OTHER_ADJUSTMENTS,
}


def _sum(expression, **kwargs):
    return Coalesce(Sum(expression, **kwargs), Value(_ZERO), output_field=_MONEY)


def _percent(part: Decimal, whole: Decimal) -> Decimal | None:
    return (part * 100 / whole).quantize(_CENT, ROUND_HALF_UP) if whole else None


def household_receipts(household: Household, period: Period) -> QuerySet[Receipt]:
    """Active, not excluded receipts in the period, in any currency."""
    start, end = period.bounds(ZoneInfo(household.timezone))
    return Receipt.objects.filter(
        household=household,
        status=Receipt.Status.ACTIVE,
        excluded_from_analytics=False,
        issued_at__gte=start,
        issued_at__lt=end,
    )


def included_receipts(household: Household, period: Period) -> QuerySet[Receipt]:
    """The receipts analytics count: those in the household's currency."""
    return household_receipts(household, period).filter(currency=household.default_currency)


# --- summary -----------------------------------------------------------------------
@dataclass
class Totals:
    period: Period
    spending: Decimal
    receipt_count: int = 0
    sales_count: int = 0
    sales_total: Decimal = _ZERO
    credit_notes_total: Decimal = _ZERO
    other_currency_receipts: int = 0

    @property
    def average_sale(self) -> Decimal | None:
        if not self.sales_count:
            return None
        return (self.sales_total / self.sales_count).quantize(_CENT, ROUND_HALF_UP)


@dataclass
class Summary:
    currency: str
    current: Totals
    previous: Totals
    needs_review_count: int

    @property
    def change_amount(self) -> Decimal:
        return self.current.spending - self.previous.spending

    @property
    def change_percent(self) -> Decimal | None:
        return _percent(self.change_amount, self.previous.spending)


def totals(household: Household, period: Period) -> Totals:
    own = Q(currency=household.default_currency)
    values = household_receipts(household, period).aggregate(
        spending=_sum(SIGNED_GROSS, filter=own),
        receipt_count=Count("id", filter=own),
        sales_count=Count("id", filter=own & Q(document_kind=SALE)),
        sales_total=_sum("gross_total", filter=own & Q(document_kind=SALE)),
        credit_notes_total=_sum("gross_total", filter=own & Q(document_kind=CREDIT_NOTE)),
        other_currency_receipts=Count("id", filter=~own),
    )
    return Totals(period=period, **values)


def summary(household: Household, period: Period) -> Summary:
    needs_review = ReceiptItem.objects.filter(
        household=household, match_status=ReceiptItem.MatchStatus.NEEDS_REVIEW
    ).count()
    return Summary(
        currency=household.default_currency,
        current=totals(household, period),
        previous=totals(household, period.previous()),
        needs_review_count=needs_review,
    )


# --- by merchant -----------------------------------------------------------------
def spending_by_merchant(household: Household, period: Period) -> list[dict]:
    return list(
        included_receipts(household, period)
        .values("merchant_id", "merchant__display_name")
        .annotate(total=_sum(SIGNED_GROSS), receipts=Count("id"))
        .order_by("-total", "merchant__display_name")
    )


# --- by category -------------------------------------------------------------------
@dataclass
class Bucket:
    bucket: str  # "category" or one of BUCKET_NAMES
    total: Decimal
    category: ProductCategory | None = None
    share: Decimal | None = None

    @property
    def name(self) -> str:
        return self.category.name if self.category else BUCKET_NAMES[self.bucket]


@dataclass
class CategoryBreakdown:
    spending: Decimal
    buckets: list[Bucket] = field(default_factory=list)


def spending_by_category(household: Household, period: Period) -> CategoryBreakdown:
    """Every line in exactly one bucket; Σ buckets = spending (requirements §13).

    Product lines: their product's category, else the merchant's default category,
    else "Uncategorized". Discount, fee and other lines: their own buckets. What the
    lines do not cover (the whole amount of summary-only receipts) goes to the
    merchant's default category, else "Unallocated".
    """
    receipts = included_receipts(household, period)
    lines = ReceiptItem.objects.filter(receipt__in=receipts).annotate(signed=SIGNED_LINE_GROSS)
    product_category = Case(
        When(
            line_type=ReceiptItem.LineType.PRODUCT,
            then=Coalesce("product__category_id", "receipt__merchant__default_category_id"),
        ),
        default=Value(None),
        output_field=UUIDField(),
    )
    line_rows = (
        lines.annotate(category_id=product_category)
        .values("line_type", "category_id")
        .annotate(total=_sum("signed"))
        .order_by()
    )
    # The remainder (receipt totals minus their lines) of every receipt goes to its
    # merchant's default category, so it is enough to compute it per default category,
    # not per receipt: Σ receipts - Σ lines, both grouped by that category. Then
    # Σ buckets = Σ lines + Σ remainders = Σ receipts = spending, even when line amounts
    # do not add up to a receipt's total (rounding, summary-only receipts).
    receipt_rows = (
        receipts.values("merchant__default_category_id")
        .annotate(total=_sum(SIGNED_GROSS))
        .order_by()
    )
    lines_per_default = {
        row["receipt__merchant__default_category_id"]: row["total"]
        for row in lines.values("receipt__merchant__default_category_id")
        .annotate(total=_sum("signed"))
        .order_by()
    }

    totals_by_key: dict[tuple[str, object], Decimal] = defaultdict(lambda: _ZERO)
    for row in line_rows:
        if row["line_type"] == ReceiptItem.LineType.PRODUCT:
            key = ("category", row["category_id"]) if row["category_id"] else (UNCATEGORIZED, None)
        else:
            key = (_LINE_BUCKETS[row["line_type"]], None)
        totals_by_key[key] += row["total"]
    spending = _ZERO
    for row in receipt_rows:
        default = row["merchant__default_category_id"]
        spending += row["total"]
        remainder = row["total"] - lines_per_default.get(default, _ZERO)
        if remainder:
            totals_by_key[("category", default) if default else (UNALLOCATED, None)] += remainder

    ids = [category_id for kind, category_id in totals_by_key if kind == "category"]
    categories = ProductCategory.objects.in_bulk(ids)
    buckets = [
        Bucket(kind, total, categories.get(category_id), _percent(total, spending))
        for (kind, category_id), total in totals_by_key.items()
        if total
    ]
    buckets.sort(key=lambda bucket: (-bucket.total, bucket.name))
    return CategoryBreakdown(spending=spending, buckets=buckets)


# --- monthly trend -------------------------------------------------------------------
def monthly_trend(household: Household, period: Period) -> list[dict]:
    """One row per calendar month of ``period`` (household timezone); empty months are 0."""
    # Truncate in the household timezone: a receipt issued at 00:30 local time on the
    # 1st belongs to that month, although it is still the previous month in UTC.
    tz = ZoneInfo(household.timezone)
    rows = (
        included_receipts(household, period)
        .annotate(month=TruncMonth("issued_at", tzinfo=tz))
        .values("month")
        .annotate(total=_sum(SIGNED_GROSS), receipts=Count("id"))
        .order_by("month")
    )
    by_month = {row["month"].date(): row for row in rows}
    months, month = [], period.first
    while month <= period.last:
        row = by_month.get(month, {"total": _ZERO, "receipts": 0})
        months.append({"month": month, "total": row["total"], "receipts": row["receipts"]})
        month = add_months(month, 1)
    return months


# --- top products --------------------------------------------------------------------
def top_products(household: Household, period: Period, *, by: str, limit: int) -> list[dict]:
    """Products by the number of receipts they were bought on, or by spend, over the
    price-history lines of the included receipts."""
    order = "-receipts" if by == "count" else "-spend"
    return list(
        ReceiptItem.objects.filter(PRICE_HISTORY, receipt__in=included_receipts(household, period))
        .values("product_id", "product__name")
        .annotate(receipts=Count("receipt_id", distinct=True), spend=_sum("gross_amount"))
        .order_by(order, "product__name")[:limit]
    )
