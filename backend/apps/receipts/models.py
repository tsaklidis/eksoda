"""Import jobs, receipts and receipt lines (requirements §6, §8.6, §8.7, §8.11, TD §8.2).

Only what the API filters, sorts or aggregates on is a column. Everything else the
source provides stays in ``Receipt.source_data`` (the canonical receipt without its
URL). Personal data never reaches these tables: the parsers do not extract it.
"""

from urllib.parse import urlsplit

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.fields import (
    MoneyField,
    NormalizedQuantityField,
    QuantityField,
    RateField,
    UnitPriceField,
)
from apps.common.models import UUIDModel
from apps.receipts.classification import LineType as _LineType
from apps.receipts.mydata import DocumentKind
from apps.receipts.mydata import Unit as CanonicalUnit

# API limit for user notes on receipts and lines (the columns are unbounded text).
USER_NOTE_MAX_LENGTH = 2000


class ReceiptImportJob(UUIDModel):
    """One receipt URL identity submitted by a household (requirements §6.3, §6.4).

    ``next_attempt_at`` is both the due time and the claim lease: a worker that claims
    the job moves it a few minutes ahead, so a crashed worker's job becomes due again.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class Outcome(models.TextChoices):
        CREATED = "created", "Created"
        DUPLICATE = "duplicate", "Duplicate"
        RECEIPT_DELETED = "receipt_deleted", "Receipt deleted"

    household = models.ForeignKey(
        "households.Household", on_delete=models.CASCADE, related_name="import_jobs"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    provider_code = models.CharField(max_length=32)
    url_identity = models.CharField(max_length=200)
    submitted_url = models.TextField(help_text="Canonical receipt URL. Sensitive: a credential.")
    url_fingerprint = models.CharField(max_length=64, db_index=True)
    issuer_vat = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=40, blank=True)
    last_error_message = models.CharField(max_length=255, blank=True)
    receipt = models.ForeignKey(
        "receipts.Receipt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="import_jobs",
    )
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["household", "provider_code", "url_identity"], name="uniq_job_identity"
            ),
            models.CheckConstraint(
                condition=Q(status="completed", outcome__isnull=False)
                | (~Q(status="completed") & Q(outcome__isnull=True)),
                name="job_outcome_iff_completed",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="job_due_idx"),
            models.Index(fields=["household", "-created_at"], name="job_household_created_idx"),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.provider_code} import {self.pk} ({self.status})"

    @property
    def source_host(self) -> str:
        return urlsplit(self.submitted_url).hostname or ""

    @property
    def scheduled_retry_at(self):
        """When the next attempt runs, while a retry is scheduled.

        A pending job without an error is new or leased by a worker: its
        ``next_attempt_at`` is then the lease end, not a retry time, so it is hidden.
        """
        if self.status == self.Status.PENDING and self.last_error_code:
            return self.next_attempt_at
        return None

    @property
    def error(self) -> dict[str, str] | None:
        if not self.last_error_code:
            return None
        return {"code": self.last_error_code, "message": self.last_error_message}


class Receipt(UUIDModel):
    class Kind(models.TextChoices):
        SALE = DocumentKind.SALE.value, "Sale"
        CREDIT_NOTE = DocumentKind.CREDIT_NOTE.value, "Credit note"
        OTHER = DocumentKind.OTHER.value, "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentMethod(models.TextChoices):
        CARD = "card", "Card"
        CASH = "cash", "Cash"
        BANK = "bank", "Bank transfer"
        MIXED = "mixed", "Mixed"
        OTHER = "other", "Other"
        UNKNOWN = "unknown", "Unknown"

    household = models.ForeignKey(
        "households.Household", on_delete=models.CASCADE, related_name="receipts"
    )
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    merchant = models.ForeignKey(
        "merchants.Merchant", on_delete=models.PROTECT, related_name="receipts"
    )
    store = models.ForeignKey(
        "merchants.Store",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="receipts",
    )
    provider_code = models.CharField(max_length=32)
    parser_version = models.CharField(max_length=20)
    # Identity (requirements §6.3).
    issuer_country = models.CharField(max_length=2)
    issuer_vat = models.CharField(max_length=20)
    uid = models.CharField(max_length=64, null=True, blank=True)
    mark = models.CharField(max_length=32, null=True, blank=True)
    cancellation_mark = models.CharField(max_length=32, null=True, blank=True)
    source_key = models.CharField(max_length=80, null=True, blank=True)
    # Document.
    document_kind = models.CharField(max_length=12, choices=Kind.choices)
    document_type_code = models.CharField(max_length=8, null=True, blank=True)
    document_number = models.CharField(max_length=100, blank=True)
    issued_at = models.DateTimeField()
    currency = models.CharField(max_length=3, default="EUR")
    # Source totals, never altered.
    gross_total = MoneyField()
    net_total = MoneyField(null=True, blank=True)
    vat_total = MoneyField(null=True, blank=True)
    discount_total = MoneyField(null=True, blank=True)
    payment_method = models.CharField(
        max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.UNKNOWN
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    validation_warnings = models.JSONField(default=list, blank=True)
    # User-editable.
    excluded_from_analytics = models.BooleanField(default=False)
    user_note = models.TextField(blank=True)
    # Sensitive: the URL works as a credential (requirements §15.3).
    source_url = models.TextField()
    source_url_fingerprint = models.CharField(max_length=64)
    source_data = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["household", "mark"],
                condition=Q(mark__isnull=False),
                name="uniq_receipt_mark",
            ),
            models.UniqueConstraint(
                fields=["household", "issuer_country", "issuer_vat", "uid"],
                condition=Q(uid__isnull=False),
                name="uniq_receipt_uid",
            ),
            models.UniqueConstraint(
                fields=["household", "source_key"],
                condition=Q(source_key__isnull=False),
                name="uniq_receipt_source_key",
            ),
        ]
        indexes = [
            models.Index(fields=["household", "-issued_at"], name="receipt_household_issued_idx"),
            models.Index(
                fields=["household", "merchant", "issued_at"], name="receipt_merchant_issued_idx"
            ),
        ]
        ordering = ("-issued_at",)

    def __str__(self) -> str:
        return f"{self.document_number or self.pk} ({self.issued_at:%Y-%m-%d})"

    @property
    def has_warnings(self) -> bool:
        return bool(self.validation_warnings)


class ReceiptItem(UUIDModel):
    class LineType(models.TextChoices):
        PRODUCT = _LineType.PRODUCT.value, "Product"
        DISCOUNT = _LineType.DISCOUNT.value, "Discount"
        FEE = _LineType.FEE.value, "Fee"
        OTHER = _LineType.OTHER.value, "Other"

    class Unit(models.TextChoices):
        PIECE = CanonicalUnit.PIECE.value, "Piece"
        KG = CanonicalUnit.KG.value, "Kilogram"
        L = CanonicalUnit.L.value, "Liter"
        OTHER = CanonicalUnit.OTHER.value, "Other"

    class NormalizedUnit(models.TextChoices):
        KG = "kg", "Kilogram"
        L = "l", "Liter"
        PIECE = "piece", "Piece"
        OTHER = "other", "Other"

    class MatchStatus(models.TextChoices):
        MATCHED = "matched", "Matched"
        NEEDS_REVIEW = "needs_review", "Needs review"
        NOT_A_PRODUCT = "not_a_product", "Not a product"

    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="items")
    household = models.ForeignKey(
        "households.Household", on_delete=models.CASCADE, related_name="+"
    )  # denormalized: always receipt.household (set by the import service)
    line_number = models.PositiveIntegerField()
    line_type = models.CharField(max_length=10, choices=LineType.choices)
    description = models.TextField()  # the original; never modified
    normalized_description = models.TextField(blank=True)
    merchant_product_code = models.CharField(max_length=100, null=True, blank=True)
    quantity = QuantityField(null=True, blank=True)
    unit = models.CharField(max_length=6, choices=Unit.choices, null=True, blank=True)
    unit_price = UnitPriceField(null=True, blank=True)
    gross_amount = MoneyField()  # after any line discount
    net_amount = MoneyField(null=True, blank=True)
    vat_rate = RateField(null=True, blank=True)
    vat_amount = MoneyField(null=True, blank=True)
    discount_amount = MoneyField(null=True, blank=True)
    # RESTRICT, not PROTECT: deleting a household deletes its products and lines together.
    product = models.ForeignKey(
        "products.Product",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="receipt_items",
    )
    match_status = models.CharField(max_length=14, choices=MatchStatus.choices)
    # Derived by apps.products.prices (requirements §11.1); null when not computable.
    normalized_quantity = NormalizedQuantityField(null=True, blank=True)
    normalized_unit = models.CharField(
        max_length=6, choices=NormalizedUnit.choices, null=True, blank=True
    )
    normalized_unit_price = UnitPriceField(null=True, blank=True)
    user_note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["receipt", "line_number"], name="uniq_item_line"),
            models.CheckConstraint(
                condition=Q(product__isnull=False, match_status="matched")
                | Q(product__isnull=True, match_status__in=["needs_review", "not_a_product"]),
                name="item_product_iff_matched",
            ),
            models.CheckConstraint(
                condition=Q(line_type="product", match_status__in=["matched", "needs_review"])
                | (~Q(line_type="product") & Q(match_status="not_a_product")),
                name="item_not_a_product_iff_non_product",
            ),
        ]
        indexes = [
            models.Index(fields=["household", "match_status"], name="item_household_match_idx"),
        ]
        ordering = ("receipt", "line_number")

    def __str__(self) -> str:
        return f"{self.line_number}. {self.description}"
