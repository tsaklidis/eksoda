from rest_framework import serializers

from apps.merchants.models import Merchant, Store
from apps.products.api.serializers import CategorySummarySerializer, MerchantRefSerializer


class MerchantSerializer(serializers.ModelSerializer):
    default_category = CategorySummarySerializer(read_only=True, allow_null=True)
    receipt_count = serializers.IntegerField(read_only=True, help_text="Your receipts here.")
    last_receipt_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Merchant
        fields = [
            "id",
            "display_name",
            "legal_name",
            "vat_number",
            "country_code",
            "street",
            "street_number",
            "city",
            "postal_code",
            "default_category",
            "receipt_count",
            "last_receipt_at",
        ]
        read_only_fields = fields


class StoreSerializer(serializers.ModelSerializer):
    merchant = MerchantRefSerializer(read_only=True)
    name = serializers.CharField(source="label", read_only=True)
    receipt_count = serializers.IntegerField(read_only=True, help_text="Your receipts here.")
    last_receipt_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Store
        fields = [
            "id",
            "merchant",
            "name",
            "branch_number",
            "street",
            "city",
            "postal_code",
            "receipt_count",
            "last_receipt_at",
        ]
        read_only_fields = fields
