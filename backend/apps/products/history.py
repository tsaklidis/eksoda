"""Price history statistics and cross-merchant comparison (requirements §11.2, §11.3).

Entries are receipt lines in PRICE_HISTORY. Statistics are per normalized unit and
currency; the average is quantity-weighted (Σ gross ÷ Σ normalized quantity).
Merchants are ranked only when at least two of them have prices in the same unit
and currency, so a shop is never shown as cheaper on incompatible units.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import QuerySet
from django.utils import timezone

from apps.households.models import Household
from apps.products.models import Product
from apps.products.prices import PRICE_HISTORY
from apps.receipts.models import ReceiptItem

_PRICE_PLACES = Decimal("0.0001")

NO_PRICES = "no_prices"
UNKNOWN_UNIT = "unknown_unit"
ONE_MERCHANT = "one_merchant"


@dataclass
class PriceStats:
    normalized_unit: str
    currency: str
    count: int
    latest: Decimal
    previous: Decimal | None
    minimum: Decimal
    maximum: Decimal
    average: Decimal  # quantity-weighted


@dataclass
class MerchantPrices:
    merchant_id: object
    merchant_name: str
    stats: PriceStats
    rank: int | None = None


@dataclass
class Comparison:
    comparable: bool
    reason: str | None
    normalized_unit: str | None
    currency: str | None
    merchants: list[MerchantPrices] = field(default_factory=list)
    available_units: list[dict] = field(default_factory=list)


def price_entries(
    product: Product,
    *,
    household: Household,
    issued_from: date | None = None,
    issued_to: date | None = None,
    merchant=None,
    store=None,
    normalized_unit: str | None = None,
) -> QuerySet[ReceiptItem]:
    """The product's price observations, newest first. Dates are household-local."""
    entries = ReceiptItem.objects.filter(PRICE_HISTORY, household=household, product=product)
    if issued_from:
        entries = entries.filter(receipt__issued_at__gte=_start_of_day(issued_from))
    if issued_to:
        entries = entries.filter(receipt__issued_at__lt=_start_of_day(issued_to + timedelta(1)))
    if merchant:
        entries = entries.filter(receipt__merchant=merchant)
    if store:
        entries = entries.filter(receipt__store=store)
    if normalized_unit:
        entries = entries.filter(normalized_unit=normalized_unit)
    return entries.select_related("receipt__merchant", "receipt__store").order_by(
        "-receipt__issued_at", "-line_number"
    )


def price_stats(entries: Iterable[ReceiptItem]) -> list[PriceStats]:
    """Statistics per (normalized unit, currency), for entries ordered newest first."""
    return [_stats(unit, currency, group) for (unit, currency), group in _groups(entries).items()]


def compare(entries: Iterable[ReceiptItem], *, normalized_unit: str | None = None) -> Comparison:
    """Per-merchant statistics in one (unit, currency) group: the requested unit, else the
    group with the most entries."""
    groups = _groups(entries)
    available = [
        {"normalized_unit": unit, "currency": currency, "count": len(group)}
        for (unit, currency), group in groups.items()
    ]
    if normalized_unit:
        groups = {key: group for key, group in groups.items() if key[0] == normalized_unit}
    if not groups:
        return Comparison(False, NO_PRICES, normalized_unit, None, available_units=available)

    (unit, currency), group = max(groups.items(), key=lambda kv: (len(kv[1]), kv[0]))
    by_merchant: dict[object, list[ReceiptItem]] = defaultdict(list)
    for entry in group:
        by_merchant[entry.receipt.merchant_id].append(entry)
    merchants = [
        MerchantPrices(
            merchant_id, items[0].receipt.merchant.display_name, _stats(unit, currency, items)
        )
        for merchant_id, items in by_merchant.items()
    ]
    merchants.sort(key=lambda row: (row.stats.average, row.merchant_name))

    if unit == ReceiptItem.NormalizedUnit.OTHER:
        reason = UNKNOWN_UNIT
    elif len(merchants) < 2:
        reason = ONE_MERCHANT
    else:
        reason = None
        for rank, row in enumerate(merchants, start=1):
            row.rank = rank
    return Comparison(reason is None, reason, unit, currency, merchants, available)


def _groups(entries: Iterable[ReceiptItem]) -> dict[tuple[str, str], list[ReceiptItem]]:
    groups: dict[tuple[str, str], list[ReceiptItem]] = defaultdict(list)
    for entry in entries:
        groups[(entry.normalized_unit, entry.receipt.currency)].append(entry)
    return dict(groups)


def _stats(unit: str, currency: str, entries: list[ReceiptItem]) -> PriceStats:
    prices = [entry.normalized_unit_price for entry in entries]  # newest first
    gross = sum((entry.gross_amount for entry in entries), Decimal(0))
    quantity = sum((entry.normalized_quantity for entry in entries), Decimal(0))
    return PriceStats(
        normalized_unit=unit,
        currency=currency,
        count=len(entries),
        latest=prices[0],
        previous=prices[1] if len(prices) > 1 else None,
        minimum=min(prices),
        maximum=max(prices),
        average=(gross / quantity).quantize(_PRICE_PLACES, ROUND_HALF_UP),
    )


def _start_of_day(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.get_current_timezone())
