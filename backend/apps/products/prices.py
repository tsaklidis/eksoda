"""Normalized unit prices on receipt lines (requirements §11.1, TD §13.4).

Price history is a query over receipt lines: each product line with a product
carries its quantity in a base unit and its price per base unit. ``refresh_prices``
recomputes them after an import, a link, a merge, a reclassification or a package
size change. A price is null when it cannot be computed, never a misleading value.
"""

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q

from apps.products.models import Product
from apps.products.units import to_base
from apps.receipts.models import Receipt, ReceiptItem

PRICE_FIELDS = ["normalized_quantity", "normalized_unit", "normalized_unit_price"]
_QUANTITY_PLACES = Decimal("0.000001")  # NormalizedQuantityField
_PRICE_PLACES = Decimal("0.0001")  # UnitPriceField

LineType = ReceiptItem.LineType
Unit = ReceiptItem.Unit
NormalizedUnit = ReceiptItem.NormalizedUnit

# Lines that count as price observations. Receipt status and kind are filters, so a
# receipt that is cancelled later needs no recomputation.
PRICE_HISTORY = Q(
    line_type=LineType.PRODUCT,
    product__isnull=False,
    normalized_unit_price__isnull=False,
    quantity__gt=0,
    gross_amount__gt=0,
    receipt__status=Receipt.Status.ACTIVE,
    receipt__document_kind=Receipt.Kind.SALE,
)


def normalize(
    item: ReceiptItem, product: Product | None
) -> tuple[Decimal | None, str | None, Decimal | None]:
    """(normalized quantity, normalized unit, price per normalized unit) for a line."""
    if item.line_type != LineType.PRODUCT or product is None or item.quantity is None:
        return None, None, None
    if item.unit in (Unit.KG, Unit.L):  # weighed or measured: the quantity itself
        quantity, unit = to_base(item.quantity, item.unit)
    elif item.unit == Unit.PIECE and product.package_quantity:
        package, unit = to_base(product.package_quantity, product.package_unit)
        quantity = item.quantity * package
    elif item.unit == Unit.PIECE:
        quantity, unit = item.quantity, NormalizedUnit.PIECE
    else:
        quantity, unit = item.quantity, NormalizedUnit.OTHER
    price = (
        (item.gross_amount / quantity).quantize(_PRICE_PLACES, ROUND_HALF_UP) if quantity else None
    )
    return quantity.quantize(_QUANTITY_PLACES, ROUND_HALF_UP), str(unit), price


def apply_prices(item: ReceiptItem) -> None:
    """Set the normalized fields from ``item.product`` (in memory; no save)."""
    item.normalized_quantity, item.normalized_unit, item.normalized_unit_price = normalize(
        item, item.product
    )


def refresh_prices(items: Iterable[ReceiptItem]) -> None:
    """Recompute and save the normalized fields (items with their product loaded)."""
    items = list(items)
    for item in items:
        apply_prices(item)
    if items:
        ReceiptItem.objects.bulk_update(items, PRICE_FIELDS)


def refresh_product_prices(product: Product) -> None:
    refresh_prices(product.receipt_items.select_related("product"))
