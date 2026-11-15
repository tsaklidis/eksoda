"""Match product lines that have no product yet (e.g. receipts imported before M4).

Receipts are processed oldest first, each in its own transaction, so the earliest
purchase of an item creates its product and later ones match it. Lines a person
linked are never changed, and running the command again changes nothing.
"""

from django.core.management.base import BaseCommand

from apps.products.matching import rematch_receipt
from apps.receipts.models import Receipt, ReceiptItem


class Command(BaseCommand):
    help = "Match receipt lines that have no product yet."

    def add_arguments(self, parser):
        parser.add_argument("--household", help="Only this household (id).")

    def handle(self, *args, household=None, **options):
        receipts = Receipt.objects.filter(
            items__line_type=ReceiptItem.LineType.PRODUCT, items__product__isnull=True
        ).distinct()
        if household:
            receipts = receipts.filter(household_id=household)
        scanned = matched = 0
        for receipt in receipts.select_related("merchant").order_by("issued_at", "id"):
            matched += rematch_receipt(receipt)
            scanned += 1
        self.stdout.write(f"Receipts scanned: {scanned}. Lines matched: {matched}.")
