from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.products.api.serializers import (
    CategorySummarySerializer,
    MerchantRefSerializer,
    ProductSummarySerializer,
)


def _money(**kwargs):
    return serializers.DecimalField(max_digits=14, decimal_places=2, **kwargs)


def _percent(**kwargs):
    return serializers.DecimalField(max_digits=9, decimal_places=2, allow_null=True, **kwargs)


# --- query parameters ---------------------------------------------------------------
# ``from`` is a Python keyword and cannot be a class attribute, so the serializers with
# a ``from`` field build it in get_fields().
class PeriodQuerySerializer(serializers.Serializer):
    """``from`` and ``to``: inclusive dates in the household timezone."""

    def get_fields(self):
        return {
            "from": serializers.DateField(required=False),
            "to": serializers.DateField(required=False),
            **super().get_fields(),
        }

    def validate(self, attrs):
        if "from" in attrs and "to" in attrs and attrs["to"] < attrs["from"]:
            raise serializers.ValidationError({"to": "Must not be before `from`."})
        return attrs


class TrendQuerySerializer(serializers.Serializer):
    to = serializers.DateField(required=False)
    months = serializers.IntegerField(required=False, min_value=1, max_value=36)


class TopProductsQuerySerializer(PeriodQuerySerializer):
    by = serializers.ChoiceField(choices=["count", "spend"], required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50)


# --- shared parts ---------------------------------------------------------------------
class PeriodSerializer(serializers.Serializer):
    def get_fields(self):
        return {
            "from": serializers.DateField(source="first"),
            "to": serializers.DateField(source="last"),
        }


class AnalyticsSerializer(serializers.Serializer):
    """Every analytics response states its period and currency."""

    period = PeriodSerializer()
    currency = serializers.CharField(help_text="Only receipts in this currency are counted.")


# --- summary ---------------------------------------------------------------------------
class TotalsSerializer(serializers.Serializer):
    period = PeriodSerializer()
    spending = _money(help_text="Σ gross totals; credit notes count negative.")
    receipt_count = serializers.IntegerField()
    sales_count = serializers.IntegerField()
    average_sale = _money(allow_null=True, help_text="Average gross total of sales.")
    credit_notes_total = _money()
    other_currency_receipts = serializers.IntegerField(
        help_text="Receipts in another currency than the household's (not counted)."
    )


class PreviousSerializer(serializers.Serializer):
    period = PeriodSerializer()
    spending = _money()


class ChangeSerializer(serializers.Serializer):
    amount = _money(source="change_amount")
    percent = _percent(source="change_percent", help_text="Null if the previous period was 0.")


class SummarySerializer(serializers.Serializer):
    currency = serializers.CharField()
    current = TotalsSerializer()
    previous = PreviousSerializer()
    change = ChangeSerializer(source="*")
    needs_review_count = serializers.IntegerField(help_text="Lines waiting for review (all time).")


# --- breakdowns ------------------------------------------------------------------------
class MerchantRowSerializer(serializers.Serializer):
    merchant = serializers.SerializerMethodField()
    total = _money()
    receipts = serializers.IntegerField()

    @extend_schema_field(MerchantRefSerializer)
    def get_merchant(self, row) -> dict:
        return {"id": str(row["merchant_id"]), "display_name": row["merchant__display_name"]}


class MerchantSpendingSerializer(AnalyticsSerializer):
    total = _money()
    merchants = MerchantRowSerializer(many=True)


class BucketSerializer(serializers.Serializer):
    bucket = serializers.ChoiceField(
        choices=[
            "category",
            "uncategorized",
            "discounts",
            "fees_deposits",
            "other_adjustments",
            "unallocated",
        ],
        help_text="`category` for a category; otherwise a bucket for lines without one.",
    )
    category = CategorySummarySerializer(allow_null=True)
    name = serializers.CharField()
    total = _money()
    share = _percent(help_text="Percent of spending.")


class CategorySpendingSerializer(AnalyticsSerializer):
    total = _money(help_text="Spending: the buckets add up to it.")
    buckets = BucketSerializer(many=True)


class MonthSerializer(serializers.Serializer):
    month = serializers.DateField(help_text="The first day of the month.")
    total = _money()
    receipts = serializers.IntegerField()


class TrendSerializer(AnalyticsSerializer):
    months = MonthSerializer(many=True)


class TopProductSerializer(serializers.Serializer):
    product = serializers.SerializerMethodField()
    receipts = serializers.IntegerField(help_text="Distinct receipts it was bought on.")
    spend = _money()

    @extend_schema_field(ProductSummarySerializer)
    def get_product(self, row) -> dict:
        return {"id": str(row["product_id"]), "name": row["product__name"]}


class TopProductsSerializer(AnalyticsSerializer):
    by = serializers.ChoiceField(choices=["count", "spend"])
    products = TopProductSerializer(many=True)
