"""Merchants and stores the household has bought from (requirements §12.8, D11).

Merchants and stores are shared public data, so a household reaches them only
through its own receipts: one it never bought from answers 404.
"""

import django_filters
from django.db.models import Count, Max
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from apps.common.households import HouseholdScopedMixin
from apps.merchants.api.serializers import MerchantSerializer, StoreSerializer
from apps.merchants.models import Merchant, Store


def _with_household_receipts(queryset, household):
    """Keep those the household has receipts from, with its receipt count and latest date.

    The filter comes before ``annotate`` on purpose: the aggregates then reuse the
    filtered join and count only this household's receipts.
    """
    return queryset.filter(receipts__household=household).annotate(
        receipt_count=Count("receipts"),
        last_receipt_at=Max("receipts__issued_at"),
    )


@extend_schema(tags=["merchants"])
class MerchantViewSet(HouseholdScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Merchant.objects.select_related("default_category")
    serializer_class = MerchantSerializer
    ordering_fields = ["display_name", "receipt_count", "last_receipt_at"]
    ordering = ["display_name"]

    def scope_queryset(self, queryset, household):
        return _with_household_receipts(queryset, household)


class StoreFilter(django_filters.FilterSet):
    merchant = django_filters.UUIDFilter(field_name="merchant_id")

    class Meta:
        model = Store
        fields = ["merchant"]


@extend_schema(tags=["merchants"])
class StoreViewSet(HouseholdScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Store.objects.select_related("merchant")
    serializer_class = StoreSerializer
    filterset_class = StoreFilter
    ordering_fields = ["receipt_count", "last_receipt_at"]
    ordering = ["merchant__display_name", "branch_number", "street"]

    def scope_queryset(self, queryset, household):
        return _with_household_receipts(queryset, household)
