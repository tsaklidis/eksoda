from django.db.models import Q
from django.utils.text import slugify
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.products import history
from apps.products.models import Product, ProductCategory
from apps.receipts.models import USER_NOTE_MAX_LENGTH, ReceiptItem

MAX_MERGE_SOURCES = 50


class CategorySummarySerializer(serializers.ModelSerializer):
    is_system = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProductCategory
        fields = ["id", "name", "slug", "is_system"]
        read_only_fields = fields


class ProductSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name"]
        read_only_fields = fields


class HouseholdContextMixin:
    """Validates ids against the household in ``context["household"]``."""

    @property
    def household(self):
        return self.context["household"]


class ProductSerializer(HouseholdContextMixin, serializers.ModelSerializer):
    category = CategorySummarySerializer(read_only=True, allow_null=True)
    category_id = serializers.UUIDField(
        write_only=True,
        required=False,
        allow_null=True,
        help_text="A system category or one of the household's.",
    )
    line_count = serializers.IntegerField(
        read_only=True, help_text="Receipt lines linked to the product."
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "brand",
            "category",
            "category_id",
            "package_quantity",
            "package_unit",
            "line_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_category_id(self, value):
        if value is None:
            return None
        category = ProductCategory.objects.filter(
            Q(household__isnull=True) | Q(household=self.household), pk=value
        ).first()
        if category is None:
            raise serializers.ValidationError("Unknown category.")
        return category

    def validate_package_quantity(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Must be greater than zero.")
        return value

    def validate(self, attrs):
        if "category_id" in attrs:
            attrs["category"] = attrs.pop("category_id")
        quantity = attrs.get("package_quantity", getattr(self.instance, "package_quantity", None))
        unit = attrs.get("package_unit", getattr(self.instance, "package_unit", None))
        if (quantity is None) != (unit is None):
            raise serializers.ValidationError(
                {"package_quantity": "Set the package quantity and unit together, or neither."}
            )
        return attrs


class ReceiptRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    issued_at = serializers.DateTimeField()
    merchant_name = serializers.CharField(source="merchant.display_name")
    currency = serializers.CharField()


class ReviewItemSerializer(serializers.ModelSerializer):
    """A receipt line with its receipt and product, as shown in review."""

    receipt = ReceiptRefSerializer(read_only=True)
    product = ProductSummarySerializer(read_only=True, allow_null=True)

    class Meta:
        model = ReceiptItem
        fields = [
            "id",
            "receipt",
            "line_number",
            "line_type",
            "description",
            "merchant_product_code",
            "quantity",
            "unit",
            "unit_price",
            "gross_amount",
            "product",
            "match_status",
            "normalized_quantity",
            "normalized_unit",
            "normalized_unit_price",
            "user_note",
        ]
        read_only_fields = fields


class ReceiptItemUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptItem
        fields = ["line_type", "user_note"]
        extra_kwargs = {
            "line_type": {"required": False},
            "user_note": {"required": False, "max_length": USER_NOTE_MAX_LENGTH},
        }


class MatchSerializer(HouseholdContextMixin, serializers.Serializer):
    product_id = serializers.UUIDField()

    def validate_product_id(self, value):
        product = Product.objects.filter(household=self.household, pk=value).first()
        if product is None:
            raise serializers.ValidationError("Unknown product.")
        return product


class MergeSerializer(HouseholdContextMixin, serializers.Serializer):
    source_product_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=MAX_MERGE_SOURCES
    )

    def validate_source_product_ids(self, value):
        ids = set(value)
        if self.context["target"].pk in ids:
            raise serializers.ValidationError("A product cannot be merged into itself.")
        products = list(Product.objects.filter(household=self.household, pk__in=ids))
        if len(products) != len(ids):
            raise serializers.ValidationError("Unknown product.")
        return products


# --- price history ---------------------------------------------------------------
class ComparisonFilterSerializer(serializers.Serializer):
    issued_from = serializers.DateField(required=False)
    issued_to = serializers.DateField(required=False)
    normalized_unit = serializers.ChoiceField(
        choices=ReceiptItem.NormalizedUnit.choices, required=False
    )


class PriceFilterSerializer(ComparisonFilterSerializer):
    merchant = serializers.UUIDField(required=False)
    store = serializers.UUIDField(required=False)


class MerchantRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()


class StoreRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField(source="label")


class PriceEntrySerializer(serializers.ModelSerializer):
    receipt_id = serializers.UUIDField(read_only=True)
    issued_at = serializers.DateTimeField(source="receipt.issued_at", read_only=True)
    merchant = MerchantRefSerializer(source="receipt.merchant", read_only=True)
    store = StoreRefSerializer(source="receipt.store", read_only=True, allow_null=True)
    currency = serializers.CharField(source="receipt.currency", read_only=True)

    class Meta:
        model = ReceiptItem
        fields = [
            "id",
            "receipt_id",
            "issued_at",
            "merchant",
            "store",
            "description",
            "quantity",
            "unit",
            "gross_amount",
            "currency",
            "normalized_quantity",
            "normalized_unit",
            "normalized_unit_price",
        ]
        read_only_fields = fields


def _price(**kwargs):
    return serializers.DecimalField(max_digits=14, decimal_places=4, **kwargs)


class PriceStatsSerializer(serializers.Serializer):
    normalized_unit = serializers.ChoiceField(choices=ReceiptItem.NormalizedUnit.choices)
    currency = serializers.CharField()
    count = serializers.IntegerField()
    latest = _price()
    previous = _price(allow_null=True)
    minimum = _price()
    maximum = _price()
    average = _price(help_text="Quantity-weighted: total paid ÷ total normalized quantity.")


class PriceHistorySerializer(serializers.Serializer):
    """Paginated price entries plus statistics over all entries that match the filters."""

    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PriceEntrySerializer(many=True)
    stats = PriceStatsSerializer(many=True)


class MerchantPricesSerializer(serializers.Serializer):
    merchant = serializers.SerializerMethodField()
    rank = serializers.IntegerField(allow_null=True, help_text="1 = lowest average price.")
    stats = PriceStatsSerializer()

    @extend_schema_field(MerchantRefSerializer)
    def get_merchant(self, row) -> dict:
        return {"id": str(row.merchant_id), "display_name": row.merchant_name}


class AvailableUnitSerializer(serializers.Serializer):
    normalized_unit = serializers.CharField()
    currency = serializers.CharField()
    count = serializers.IntegerField()


class PriceComparisonSerializer(serializers.Serializer):
    comparable = serializers.BooleanField()
    reason = serializers.ChoiceField(
        choices=[history.NO_PRICES, history.UNKNOWN_UNIT, history.ONE_MERCHANT],
        allow_null=True,
        help_text="Why merchants are not ranked.",
    )
    normalized_unit = serializers.CharField(allow_null=True)
    currency = serializers.CharField(allow_null=True)
    merchants = MerchantPricesSerializer(many=True)
    available_units = AvailableUnitSerializer(many=True)


class CategorySerializer(HouseholdContextMixin, serializers.ModelSerializer):
    """A system or household category. The slug is derived from the name."""

    is_system = serializers.BooleanField(read_only=True)
    product_count = serializers.IntegerField(read_only=True, help_text="Your products in it.")

    class Meta:
        model = ProductCategory
        fields = ["id", "name", "slug", "is_system", "product_count"]
        read_only_fields = ["id", "slug", "is_system", "product_count"]

    def validate_name(self, value):
        # The field already trims whitespace and refuses a blank name. Names are unique
        # by slug among the system categories and the household's own.
        taken = ProductCategory.objects.filter(
            Q(household__isnull=True) | Q(household=self.household), slug=category_slug(value)
        )
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError("A category with this name exists.")
        return value

    def validate(self, attrs):
        if "name" in attrs:
            attrs["slug"] = category_slug(attrs["name"])
        return attrs


def category_slug(name: str) -> str:
    return slugify(name, allow_unicode=True)[:80] or "category"
