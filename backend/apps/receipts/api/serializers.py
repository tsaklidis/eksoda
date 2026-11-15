from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.merchants.models import Merchant, Store
from apps.products.api.serializers import ProductSummarySerializer
from apps.receipts.models import USER_NOTE_MAX_LENGTH, Receipt, ReceiptImportJob, ReceiptItem
from apps.receipts.mydata import PaymentMethod


# --- imports ---------------------------------------------------------------------
class ImportRequestSerializer(serializers.Serializer):
    url = serializers.CharField(
        trim_whitespace=False, help_text="The receipt link from the QR code (https)."
    )


class ImportErrorSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()


class ImportJobSerializer(serializers.ModelSerializer):
    """An import job. Shows the provider host, never the receipt URL (a credential)."""

    source_host = serializers.CharField(read_only=True)
    issuer_vat = serializers.SerializerMethodField()
    next_attempt_at = serializers.DateTimeField(
        source="scheduled_retry_at",
        read_only=True,
        allow_null=True,
        help_text="When the next attempt runs, while a retry is scheduled.",
    )
    error = ImportErrorSerializer(
        read_only=True, allow_null=True, help_text="The last error, if any."
    )
    receipt_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = ReceiptImportJob
        fields = [
            "id",
            "status",
            "outcome",
            "provider_code",
            "source_host",
            "issuer_vat",
            "attempt_count",
            "next_attempt_at",
            "error",
            "receipt_id",
            "created_at",
            "updated_at",
            "finished_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_issuer_vat(self, job: ReceiptImportJob) -> str | None:
        return job.issuer_vat or None


class ImportSubmitResponseSerializer(ImportJobSerializer):
    duplicate = serializers.BooleanField(
        read_only=True, help_text="This receipt link was submitted before."
    )

    class Meta(ImportJobSerializer.Meta):
        fields = [*ImportJobSerializer.Meta.fields, "duplicate"]
        read_only_fields = fields


# --- receipts --------------------------------------------------------------------
class MerchantSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ["id", "display_name", "vat_number"]
        read_only_fields = fields


class StoreSummarySerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="label", read_only=True)

    class Meta:
        model = Store
        fields = ["id", "name", "branch_number", "street", "city", "postal_code"]
        read_only_fields = fields


class ValidationWarningSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    line_number = serializers.IntegerField(allow_null=True)
    expected = serializers.CharField(allow_null=True)
    actual = serializers.CharField(allow_null=True)


class CoverageSerializer(serializers.Serializer):
    """What the source provides (requirements §7.2)."""

    line_items = serializers.BooleanField()
    line_tax_amounts = serializers.BooleanField()
    official_codes = serializers.BooleanField()
    mydata_registered = serializers.BooleanField()
    issue_time = serializers.ChoiceField(choices=["exact", "approximate", "date_only"])
    cross_checked = serializers.BooleanField()


class VatEntrySerializer(serializers.Serializer):
    rate = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    category_code = serializers.CharField(allow_null=True)
    net = serializers.DecimalField(max_digits=12, decimal_places=2)
    vat = serializers.DecimalField(max_digits=12, decimal_places=2)


class PaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    method = serializers.ChoiceField(choices=[m.value for m in PaymentMethod], allow_null=True)
    method_label = serializers.CharField(allow_null=True)
    derived = serializers.BooleanField(
        help_text="Inferred (e.g. cash = total − card), not printed by the source."
    )


class ReceiptItemSerializer(serializers.ModelSerializer):
    product = ProductSummarySerializer(read_only=True, allow_null=True)

    class Meta:
        model = ReceiptItem
        fields = [
            "id",
            "line_number",
            "line_type",
            "description",
            "merchant_product_code",
            "quantity",
            "unit",
            "unit_price",
            "gross_amount",
            "net_amount",
            "vat_rate",
            "vat_amount",
            "discount_amount",
            "product",
            "match_status",
            "normalized_quantity",
            "normalized_unit",
            "normalized_unit_price",
            "user_note",
        ]
        read_only_fields = fields


class ReceiptListSerializer(serializers.ModelSerializer):
    merchant = MerchantSummarySerializer(read_only=True)
    store = StoreSummarySerializer(read_only=True, allow_null=True)
    item_count = serializers.IntegerField(read_only=True)
    needs_review = serializers.BooleanField(
        read_only=True, help_text="Some product lines are not linked to a product yet."
    )
    has_warnings = serializers.BooleanField(read_only=True)

    class Meta:
        model = Receipt
        fields = [
            "id",
            "merchant",
            "store",
            "issued_at",
            "document_kind",
            "document_number",
            "status",
            "currency",
            "gross_total",
            "net_total",
            "vat_total",
            "discount_total",
            "payment_method",
            "item_count",
            "needs_review",
            "has_warnings",
            "excluded_from_analytics",
            "provider_code",
            "created_at",
        ]
        read_only_fields = fields


class ReceiptDetailSerializer(ReceiptListSerializer):
    validation_warnings = ValidationWarningSerializer(many=True, read_only=True)
    coverage = CoverageSerializer(
        source="source_data.coverage", read_only=True, allow_null=True, default=None
    )
    vat_breakdown = VatEntrySerializer(
        source="source_data.vat_breakdown", many=True, read_only=True, default=list
    )
    payments = PaymentSerializer(
        source="source_data.payments", many=True, read_only=True, default=list
    )
    items = ReceiptItemSerializer(many=True, read_only=True)
    source_url = serializers.CharField(
        read_only=True, help_text="The original receipt page. Works like a password."
    )

    class Meta(ReceiptListSerializer.Meta):
        fields = [
            *ReceiptListSerializer.Meta.fields,
            "document_type_code",
            "mark",
            "uid",
            "cancellation_mark",
            "parser_version",
            "validation_warnings",
            "coverage",
            "vat_breakdown",
            "payments",
            "user_note",
            "source_url",
            "items",
            "updated_at",
        ]
        read_only_fields = fields


class ReceiptUpdateSerializer(serializers.ModelSerializer):
    """The user-editable fields. Source values are read-only (requirements §12.5)."""

    store_id = serializers.UUIDField(
        source="store",  # validated into a Store (validate_store_id)
        required=False,
        allow_null=True,
        help_text="A store of the receipt's merchant.",
    )

    class Meta:
        model = Receipt
        fields = ["user_note", "excluded_from_analytics", "store_id"]
        extra_kwargs = {"user_note": {"required": False, "max_length": USER_NOTE_MAX_LENGTH}}

    def validate_store_id(self, value):
        if value is None:
            return None
        store = Store.objects.filter(pk=value, merchant_id=self.instance.merchant_id).first()
        if store is None:
            raise serializers.ValidationError("Choose a store of the receipt's merchant.")
        return store
