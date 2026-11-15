"""Matching receipt lines to household products (requirements §9.2, TD §13.2).

The key of a line is its merchant item code, or its normalized description when the
merchant prints no code. Per household and merchant:

1. A mapping exists for the key → the line is matched to the mapping's product.
   Guard (code keys only): when the description differs too much from the last one
   seen for that code, the merchant may have reused the code for another item, so
   the line goes to review and the mapping is left alone.
2. No mapping → a product is created from the line (its name is the description,
   with a package size when the description states one unambiguously) together
   with a mapping, so the item's price history starts right away (D7).

A concurrent import of the same new item loses on the mapping's unique constraint
and uses the winner's mapping.
"""

import difflib

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.merchants.models import Merchant
from apps.products.models import MerchantProductMapping, Product
from apps.products.packages import suggest
from apps.products.prices import refresh_prices
from apps.receipts.models import Receipt, ReceiptItem

LineType = ReceiptItem.LineType
MatchStatus = ReceiptItem.MatchStatus


def match_items(items: list[ReceiptItem], *, merchant: Merchant) -> None:
    for item in items:
        match_item(item, merchant=merchant)


def match_item(item: ReceiptItem, *, merchant: Merchant) -> None:
    """Set ``item.product`` and ``item.match_status``. The item itself is not saved."""
    if item.line_type != LineType.PRODUCT:
        item.product, item.match_status = None, MatchStatus.NOT_A_PRODUCT
        return

    mapping = find_mapping(item, merchant)
    # A mapping created from this very line needs neither the guard nor a description
    # update. One that a concurrent import created first (created=False) gets both.
    created = False
    if mapping is None:
        mapping, created = _create_product_and_mapping(item, merchant)
    if not created and item.merchant_product_code and _reused_code(item, mapping):
        item.product, item.match_status = None, MatchStatus.NEEDS_REVIEW
        return

    item.product, item.match_status = mapping.product, MatchStatus.MATCHED
    if not created and mapping.last_seen_description != item.description:
        remember_description(mapping, item)


def find_mapping(item: ReceiptItem, merchant: Merchant) -> MerchantProductMapping | None:
    return (
        MerchantProductMapping.objects.select_related("product")
        .filter(household_id=item.household_id, merchant=merchant, **mapping_key(item))
        .first()
    )


def mapping_key(item: ReceiptItem) -> dict:
    """The lookup for the line's key: its item code, else its normalized description."""
    if item.merchant_product_code:
        return {"merchant_product_code": item.merchant_product_code}
    return {
        "merchant_product_code__isnull": True,
        "normalized_description": item.normalized_description,
    }


def remember_description(mapping: MerchantProductMapping, item: ReceiptItem) -> None:
    """A code mapping follows the item's latest description (the guard compares to it)."""
    mapping.last_seen_description = item.description
    fields = ["last_seen_description", "updated_at"]
    if mapping.merchant_product_code:
        mapping.normalized_description = item.normalized_description
        fields.append("normalized_description")
    mapping.save(update_fields=fields)


def new_product(item: ReceiptItem) -> Product:
    """An unsaved product named after the line, with its package size when unambiguous.
    Only piece lines get one: a weighed line's quantity is already in kg or l."""
    name = item.description.strip()[:255] or f"Item {item.merchant_product_code or '?'}"
    product = Product(household_id=item.household_id, name=name)
    if item.unit == ReceiptItem.Unit.PIECE:
        package = suggest(item.description)
        if package is not None:
            product.package_quantity, product.package_unit = package.quantity, package.unit
    return product


def rematch_receipt(receipt: Receipt) -> int:
    """Match the receipt's product lines that have no product yet (lines imported before
    matching existed, or lines matching skipped). Linked lines are left alone.
    Returns the number of lines matched."""
    with transaction.atomic():
        items = list(
            receipt.items.filter(line_type=LineType.PRODUCT, product__isnull=True).order_by(
                "line_number"
            )
        )
        match_items(items, merchant=receipt.merchant)
        ReceiptItem.objects.bulk_update(items, ["product", "match_status"])
        refresh_prices(items)
    return sum(item.match_status == MatchStatus.MATCHED for item in items)


def _reused_code(item: ReceiptItem, mapping: MerchantProductMapping) -> bool:
    """The code-reuse guard. Shops give an old item code to a new item, and trusting the
    code alone would put the new item's prices in the old product's history. Small
    wording changes ("ΦΡΕΣΚΟ" → "ΦΡ.") stay above the threshold and still match."""
    ratio = difflib.SequenceMatcher(
        None, item.normalized_description, mapping.normalized_description
    ).ratio()
    return ratio < settings.MATCH_GUARD_SIMILARITY


def _create_product_and_mapping(
    item: ReceiptItem, merchant: Merchant
) -> tuple[MerchantProductMapping, bool]:
    try:
        with transaction.atomic():
            product = new_product(item)
            product.save()
            mapping = MerchantProductMapping.objects.create(
                household_id=item.household_id,
                merchant=merchant,
                merchant_product_code=item.merchant_product_code or None,
                normalized_description=item.normalized_description,
                last_seen_description=item.description,
                product=product,
            )
        return mapping, True
    except IntegrityError:  # a concurrent import created the mapping first
        mapping = find_mapping(item, merchant)
        if mapping is None:
            raise
        return mapping, False
