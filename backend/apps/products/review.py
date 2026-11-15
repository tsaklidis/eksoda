"""Corrections people make to matching (requirements §9.3, TD §13.5).

Each service runs in one transaction and recomputes the affected lines' prices.
Corrections never change source amounts or original descriptions. Callers pass
objects already scoped to one household.
"""

from django.db import transaction
from django.utils import timezone

from apps.products.errors import LineNotProduct
from apps.products.matching import mapping_key, match_item
from apps.products.models import MerchantProductMapping, Product
from apps.products.prices import (
    PRICE_FIELDS,
    apply_prices,
    refresh_prices,
    refresh_product_prices,
)
from apps.receipts.models import ReceiptItem

LineType = ReceiptItem.LineType
MatchStatus = ReceiptItem.MatchStatus
PRODUCT_FIELDS = frozenset({"name", "brand", "category", "package_quantity", "package_unit"})


def link_item(item: ReceiptItem, product: Product) -> ReceiptItem:
    """Link a product line to ``product`` and remember it for the merchant's item, so the
    next import of that item matches automatically."""
    if item.line_type != LineType.PRODUCT:
        raise LineNotProduct()
    with transaction.atomic():
        previous = item.product
        item.product, item.match_status = product, MatchStatus.MATCHED
        apply_prices(item)
        item.save(update_fields=["product", "match_status", *PRICE_FIELDS, "updated_at"])
        _remember(item, product)
        _delete_if_orphan(previous, keep=product)
    return item


def create_product_for_item(item: ReceiptItem, **values) -> ReceiptItem:
    """Create a household product from the line's details, then link the line to it."""
    if item.line_type != LineType.PRODUCT:
        raise LineNotProduct()
    with transaction.atomic():
        product = Product.objects.create(household_id=item.household_id, **values)
        return link_item(item, product)


def update_item(item: ReceiptItem, *, line_type: str | None = None, user_note: str | None = None):
    """Reclassify a line and/or change its note. Back to ``product``: matched again."""
    with transaction.atomic():
        fields = ["updated_at"]
        if user_note is not None:
            item.user_note = user_note
            fields.append("user_note")
        previous = item.product
        if line_type is not None and line_type != item.line_type:
            item.line_type = line_type
            if line_type == LineType.PRODUCT:
                match_item(item, merchant=item.receipt.merchant)
            else:
                item.product, item.match_status = None, MatchStatus.NOT_A_PRODUCT
            apply_prices(item)
            fields += ["line_type", "product", "match_status", *PRICE_FIELDS]
        item.save(update_fields=fields)
        _delete_if_orphan(previous, keep=item.product)
    return item


def update_product(product: Product, **changes) -> Product:
    """Edit a product. A package size change recomputes its lines' prices."""
    if not changes.keys() <= PRODUCT_FIELDS:
        raise ValueError(f"not editable: {sorted(changes.keys() - PRODUCT_FIELDS)}")
    package_changed = any(
        field in changes and changes[field] != getattr(product, field)
        for field in ("package_quantity", "package_unit")
    )
    with transaction.atomic():
        for field, value in changes.items():
            setattr(product, field, value)
        product.save()
        if package_changed:
            refresh_product_prices(product)
    return product


def merge_products(target: Product, sources: list[Product]) -> Product:
    """Merge ``sources`` into ``target``: their merchant mappings and lines move to the
    target, the moved lines get new prices, and the sources are deleted."""
    source_ids = [source.pk for source in sources]
    if not source_ids or target.pk in source_ids:
        raise ValueError("merge needs other products than the target")
    with transaction.atomic():
        # Lock the products so that a concurrent merge cannot delete one of them while
        # this one moves lines to it. A product deleted meanwhile fails the count check.
        locked = list(
            Product.objects.select_for_update()
            .filter(pk__in=[target.pk, *source_ids])
            .order_by("pk")
        )
        if len(locked) != len(set(source_ids)) + 1 or any(
            product.household_id != target.household_id for product in locked
        ):
            raise ValueError("products must exist and belong to the same household")
        # Mapping keys are unique per household and merchant, so they never collide.
        MerchantProductMapping.objects.filter(product_id__in=source_ids).update(
            product=target, updated_at=timezone.now()
        )
        items = list(ReceiptItem.objects.filter(product_id__in=source_ids))
        for item in items:
            item.product = target
        ReceiptItem.objects.bulk_update(items, ["product"])
        refresh_prices(items)
        Product.objects.filter(pk__in=source_ids).delete()
    return target


def _remember(item: ReceiptItem, product: Product) -> None:
    """Point the mapping of the line's key (code, else description) at ``product``."""
    MerchantProductMapping.objects.update_or_create(
        household_id=item.household_id,
        merchant_id=item.receipt.merchant_id,
        **mapping_key(item),
        defaults={
            "product": product,
            "last_seen_description": item.description,
            "normalized_description": item.normalized_description,
        },
    )


def _delete_if_orphan(product: Product | None, *, keep: Product | None) -> None:
    """Delete a product left with no lines and no mappings (e.g. a wrong auto-match)."""
    if product is None or (keep is not None and product.pk == keep.pk):
        return
    if not product.receipt_items.exists() and not product.mappings.exists():
        product.delete()
