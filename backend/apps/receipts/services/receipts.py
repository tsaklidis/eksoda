"""Changes users make to stored receipts (requirements §12.5, D10)."""

from django.db import transaction
from django.utils import timezone

from apps.receipts.models import Receipt, ReceiptImportJob

EDITABLE_FIELDS = frozenset({"user_note", "excluded_from_analytics", "store"})


def update_receipt(receipt: Receipt, **changes) -> Receipt:
    """Change user-editable fields only; source values are never changed.

    A new ``store`` must belong to the receipt's merchant (the API validates this first).
    """
    if not changes.keys() <= EDITABLE_FIELDS:
        raise ValueError(f"not editable: {sorted(changes.keys() - EDITABLE_FIELDS)}")
    store = changes.get("store")
    if store is not None and store.merchant_id != receipt.merchant_id:
        raise ValueError("the store belongs to another merchant")
    for field, value in changes.items():
        setattr(receipt, field, value)
    if changes:
        receipt.save(update_fields=[*changes, "updated_at"])
    return receipt


def delete_receipt(receipt: Receipt) -> None:
    """Hard-delete the receipt and its lines. Its import jobs are kept, marked
    ``receipt_deleted``, so resubmitting the URL imports the receipt again."""
    with transaction.atomic():
        ReceiptImportJob.objects.filter(receipt=receipt).update(
            outcome=ReceiptImportJob.Outcome.RECEIPT_DELETED, updated_at=timezone.now()
        )
        receipt.delete()
