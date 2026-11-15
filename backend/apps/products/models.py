"""Categories, household products and merchant item mappings (requirements §8.8–§8.10).

Products belong to a household. Each merchant item (its code, or its normalized
description when the receipt prints no code) maps to one product, so the next
import from that merchant matches automatically. Variants are separate products,
and products are never merged automatically.
"""

from django.db import models
from django.db.models import Q

from apps.common.fields import QuantityField
from apps.common.models import UUIDModel
from apps.common.text import normalize_text


class ProductCategory(UUIDModel):
    """A flat category: system-wide (no household) or a household's own."""

    household = models.ForeignKey(
        "households.Household",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["household", "slug"], nulls_distinct=False, name="uniq_category_slug"
            ),
        ]
        ordering = ("name",)
        verbose_name_plural = "product categories"

    def __str__(self) -> str:
        return self.name if self.household_id else f"{self.name} (system)"

    @property
    def is_system(self) -> bool:
        return self.household_id is None


class Product(UUIDModel):
    class PackageUnit(models.TextChoices):
        G = "g", "Gram"
        KG = "kg", "Kilogram"
        ML = "ml", "Milliliter"
        CL = "cl", "Centiliter"
        L = "l", "Liter"
        PIECE = "piece", "Piece"

    household = models.ForeignKey(
        "households.Household", on_delete=models.CASCADE, related_name="products"
    )
    name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255, editable=False)
    brand = models.CharField(max_length=120, blank=True)
    category = models.ForeignKey(
        ProductCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )
    package_quantity = QuantityField(null=True, blank=True)
    package_unit = models.CharField(
        max_length=6, choices=PackageUnit.choices, null=True, blank=True
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(package_quantity__isnull=True, package_unit__isnull=True)
                | Q(
                    package_quantity__isnull=False,
                    package_unit__isnull=False,
                    package_quantity__gt=0,
                ),
                name="product_package_complete",
            ),
        ]
        indexes = [models.Index(fields=["household", "name"], name="product_household_name_idx")]
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.normalized_name = normalize_text(self.name)[:255]
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "name" in update_fields:
            kwargs["update_fields"] = {*update_fields, "normalized_name"}
        super().save(*args, **kwargs)


class MerchantProductMapping(UUIDModel):
    """Which household product a merchant item is. The key is the merchant's item code,
    or the normalized description when the merchant prints no code."""

    household = models.ForeignKey(
        "households.Household", on_delete=models.CASCADE, related_name="+"
    )
    merchant = models.ForeignKey(
        "merchants.Merchant", on_delete=models.PROTECT, related_name="product_mappings"
    )
    merchant_product_code = models.CharField(max_length=100, null=True, blank=True)
    normalized_description = models.TextField()
    last_seen_description = models.TextField()
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="mappings")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["household", "merchant", "merchant_product_code"],
                condition=Q(merchant_product_code__isnull=False),
                name="uniq_mapping_code",
            ),
            models.UniqueConstraint(
                fields=["household", "merchant", "normalized_description"],
                condition=Q(merchant_product_code__isnull=True),
                name="uniq_mapping_desc",
            ),
        ]

    def __str__(self) -> str:
        key = self.merchant_product_code or self.normalized_description
        return f"{key} → {self.product_id}"
