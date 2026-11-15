from datetime import date, datetime, time, timedelta

import django_filters
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.common.text import normalize_text
from apps.receipts.models import Receipt, ReceiptImportJob, ReceiptItem


def start_of_day(day: date) -> datetime:
    """Midnight of ``day`` in the active (household) timezone."""
    return datetime.combine(day, time.min, tzinfo=timezone.get_current_timezone())


class ImportJobFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=ReceiptImportJob.Status.choices)
    created_from = django_filters.DateFilter(
        method="filter_created_from", help_text="First day (household timezone), inclusive."
    )
    created_to = django_filters.DateFilter(
        method="filter_created_to", help_text="Last day (household timezone), inclusive."
    )

    class Meta:
        model = ReceiptImportJob
        fields = ["status", "created_from", "created_to"]

    def filter_created_from(self, queryset, name, value):
        return queryset.filter(created_at__gte=start_of_day(value))

    def filter_created_to(self, queryset, name, value):
        return queryset.filter(created_at__lt=start_of_day(value + timedelta(days=1)))


class ReceiptFilter(django_filters.FilterSet):
    """Receipt filters (requirements §12.5). Line conditions use EXISTS subqueries, not
    joins, so they never duplicate receipts or inflate the annotated line counts."""

    issued_from = django_filters.DateFilter(
        method="filter_issued_from", help_text="First day (household timezone), inclusive."
    )
    issued_to = django_filters.DateFilter(
        method="filter_issued_to", help_text="Last day (household timezone), inclusive."
    )
    merchant = django_filters.UUIDFilter(field_name="merchant_id")
    store = django_filters.UUIDFilter(field_name="store_id")
    min_total = django_filters.NumberFilter(field_name="gross_total", lookup_expr="gte")
    max_total = django_filters.NumberFilter(field_name="gross_total", lookup_expr="lte")
    product = django_filters.UUIDFilter(
        method="filter_product", help_text="Receipts with a line of this product."
    )
    category = django_filters.UUIDFilter(
        method="filter_category",
        help_text="Receipts with a product of this category, or from a merchant whose "
        "default category it is.",
    )
    needs_review = django_filters.BooleanFilter(
        method="filter_needs_review", help_text="Some lines wait for review."
    )
    has_warnings = django_filters.BooleanFilter(
        method="filter_has_warnings", help_text="Validation found discrepancies."
    )
    status = django_filters.ChoiceFilter(choices=Receipt.Status.choices)
    document_kind = django_filters.ChoiceFilter(choices=Receipt.Kind.choices)
    q = django_filters.CharFilter(
        method="filter_q", help_text="Text in a line description or the merchant name."
    )

    class Meta:
        model = Receipt
        fields = [
            "issued_from",
            "issued_to",
            "merchant",
            "store",
            "min_total",
            "max_total",
            "product",
            "category",
            "needs_review",
            "has_warnings",
            "status",
            "document_kind",
            "q",
        ]

    def filter_issued_from(self, queryset, name, value):
        return queryset.filter(issued_at__gte=start_of_day(value))

    def filter_issued_to(self, queryset, name, value):
        return queryset.filter(issued_at__lt=start_of_day(value + timedelta(days=1)))

    def filter_product(self, queryset, name, value):
        return queryset.filter(Exists(_lines().filter(product_id=value)))

    def filter_category(self, queryset, name, value):
        in_category = Exists(_lines().filter(product__category_id=value))
        return queryset.filter(in_category | Q(merchant__default_category_id=value))

    def filter_needs_review(self, queryset, name, value):
        needs_review = Exists(_lines().filter(match_status=ReceiptItem.MatchStatus.NEEDS_REVIEW))
        return queryset.filter(needs_review if value else ~needs_review)

    def filter_has_warnings(self, queryset, name, value):
        empty = Q(validation_warnings=[])
        return queryset.filter(~empty if value else empty)

    def filter_q(self, queryset, name, value):
        key = normalize_text(value)
        if not key:
            return queryset
        # Lines are searched on their normalized key (accents and case removed);
        # merchant names as stored.
        in_lines = Exists(_lines().filter(normalized_description__contains=key))
        text = value.strip()
        by_merchant = Q(merchant__display_name__icontains=text) | Q(
            merchant__legal_name__icontains=text
        )
        return queryset.filter(in_lines | by_merchant)


def _lines():
    return ReceiptItem.objects.filter(receipt=OuterRef("pk"))
