"""Merchants and stores: global, public business data (requirements §8.4, §8.5, D11).

They are created and refreshed by receipt imports and curated by staff in the admin.
Users only see the merchants and stores on their own household's receipts.
"""

from django.db import models
from django.db.models import Q

from apps.common.models import UUIDModel


class Merchant(UUIDModel):
    """The legal entity that issued a receipt (not a retail brand)."""

    country_code = models.CharField(max_length=2, default="GR")
    vat_number = models.CharField(max_length=20, help_text="Digits only, without the EL prefix.")
    legal_name = models.CharField(max_length=255)
    display_name = models.CharField(
        max_length=120, help_text="Derived from the legal name until staff change it."
    )
    activity_description = models.TextField(blank=True)
    tax_office = models.CharField(max_length=120, blank=True)
    gemi_number = models.CharField(max_length=32, blank=True)
    street = models.CharField(max_length=255, blank=True)
    street_number = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    details_as_of = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Issue time of the newest receipt that set the public details.",
    )
    default_category = models.ForeignKey(
        "products.ProductCategory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        limit_choices_to={"household__isnull": True},
        help_text="System category for spending at this merchant when products have none.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["country_code", "vat_number"], name="uniq_merchant_vat"
            ),
        ]
        ordering = ("display_name",)

    def __str__(self) -> str:
        return f"{self.display_name} ({self.country_code}{self.vat_number})"


class Store(UUIDModel):
    """A branch of a merchant: matched by branch number, else by normalized address."""

    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name="stores")
    branch_number = models.CharField(max_length=16, null=True, blank=True)
    display_name = models.CharField(max_length=120, blank=True)
    street = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    country_code = models.CharField(max_length=2, default="GR")
    normalized_address = models.CharField(max_length=400, blank=True)
    details_as_of = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["merchant", "branch_number"],
                condition=Q(branch_number__isnull=False),
                name="uniq_store_branch",
            ),
            models.UniqueConstraint(
                fields=["merchant", "normalized_address"],
                condition=Q(branch_number__isnull=True) & ~Q(normalized_address=""),
                name="uniq_store_address",
            ),
        ]
        ordering = ("merchant", "branch_number", "street")

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        """The staff-set name, else the address, else the branch number."""
        address = ", ".join(part for part in (self.street, self.city) if part)
        return self.display_name or address or f"#{self.branch_number or '?'}"
