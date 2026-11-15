"""Household categories (requirements §8.9, §12.8). System categories are read-only."""

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.households.models import Household
from apps.products.errors import CategoryInUse, SystemCategoryReadOnly
from apps.products.models import Product, ProductCategory

_NAME_TAKEN = {"name": ["A category with this name exists."]}


def create_category(household: Household, *, name: str, slug: str) -> ProductCategory:
    try:
        with transaction.atomic():
            return ProductCategory.objects.create(household=household, name=name, slug=slug)
    except IntegrityError:  # a concurrent request took the slug
        raise ValidationError(_NAME_TAKEN) from None


def update_category(category: ProductCategory, *, name: str, slug: str) -> ProductCategory:
    if category.is_system:
        raise SystemCategoryReadOnly()
    category.name, category.slug = name, slug
    try:
        with transaction.atomic():
            category.save(update_fields=["name", "slug", "updated_at"])
    except IntegrityError:
        raise ValidationError(_NAME_TAKEN) from None
    return category


def delete_category(category: ProductCategory) -> None:
    if category.is_system:
        raise SystemCategoryReadOnly()
    if Product.objects.filter(category=category).exists():
        raise CategoryInUse()
    category.delete()
