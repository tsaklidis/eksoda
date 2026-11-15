import django_filters
from django.db.models import Exists, OuterRef

from apps.common.text import normalize_text
from apps.products.models import MerchantProductMapping, Product


class ProductFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="filter_q", help_text="Substring of the name (accents and case ignored)."
    )
    category = django_filters.UUIDFilter(field_name="category_id")
    brand = django_filters.CharFilter(field_name="brand", lookup_expr="iexact")
    merchant = django_filters.UUIDFilter(
        method="filter_merchant", help_text="Products bought at this merchant."
    )

    class Meta:
        model = Product
        fields = ["q", "category", "brand", "merchant"]

    def filter_q(self, queryset, name, value):
        key = normalize_text(value)
        return queryset.filter(normalized_name__contains=key) if key else queryset

    def filter_merchant(self, queryset, name, value):
        # Exists, not a join: a join would multiply the annotated line counts.
        mapped = MerchantProductMapping.objects.filter(product=OuterRef("pk"), merchant_id=value)
        return queryset.filter(Exists(mapped))
