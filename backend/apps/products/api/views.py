"""Product, price history, review and category endpoints (requirements §12.6–§12.8).

All are household-scoped through the X-Household-ID header: other households'
products, lines and categories answer 404.
"""

from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.households import HouseholdScopedMixin
from apps.products import categories, history
from apps.products import review as review_services
from apps.products.api.filters import ProductFilter
from apps.products.api.serializers import (
    CategorySerializer,
    ComparisonFilterSerializer,
    MatchSerializer,
    MergeSerializer,
    PriceComparisonSerializer,
    PriceEntrySerializer,
    PriceFilterSerializer,
    PriceHistorySerializer,
    PriceStatsSerializer,
    ProductSerializer,
    ReceiptItemUpdateSerializer,
    ReviewItemSerializer,
)
from apps.products.errors import SystemCategoryReadOnly
from apps.products.models import Product, ProductCategory
from apps.receipts.models import ReceiptItem


def _query(serializer_class) -> list[OpenApiParameter]:
    """Document a query-parameter serializer as OpenAPI parameters."""
    return [
        OpenApiParameter(name, location=OpenApiParameter.QUERY)
        for name in serializer_class().fields
    ]


class HouseholdSerializerContextMixin(HouseholdScopedMixin):
    """Passes the household to serializers, which check ids against it. OpenAPI
    generation builds serializers without a request (no ``household``)."""

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if hasattr(self, "household"):
            context["household"] = self.household
        return context


@extend_schema(tags=["products"])
@extend_schema_view(
    partial_update=extend_schema(description="A package size change recomputes line prices."),
)
class ProductViewSet(
    HouseholdSerializerContextMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filterset_class = ProductFilter
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("category")
            .annotate(line_count=Count("receipt_items"))
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = serializer.save(household=self.household)
        product = self.get_queryset().get(pk=created.pk)  # with its line count
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        product = self.get_object()
        serializer = self.get_serializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        review_services.update_product(product, **serializer.validated_data)
        return Response(ProductSerializer(self.get_object()).data)

    @extend_schema(parameters=_query(PriceFilterSerializer), responses=PriceHistorySerializer)
    @action(detail=True, methods=["get"])
    def prices(self, request, pk=None):
        """Price history: one entry per receipt line, plus statistics per unit."""
        filters = PriceFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        entries = history.price_entries(
            self.get_object(), household=self.household, **filters.validated_data
        )
        page = self.paginate_queryset(entries)
        response = self.get_paginated_response(PriceEntrySerializer(page, many=True).data)
        stats = history.price_stats(entries)  # over every matching entry, not just this page
        response.data["stats"] = PriceStatsSerializer(stats, many=True).data
        return response

    @extend_schema(
        parameters=_query(ComparisonFilterSerializer), responses=PriceComparisonSerializer
    )
    @action(detail=True, methods=["get"], url_path="price-comparison")
    def price_comparison(self, request, pk=None):
        """Prices per merchant in one normalized unit. Ranked only when comparable."""
        filters = ComparisonFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        unit = filters.validated_data.pop("normalized_unit", None)
        entries = history.price_entries(
            self.get_object(), household=self.household, **filters.validated_data
        )
        comparison = history.compare(entries, normalized_unit=unit)
        return Response(PriceComparisonSerializer(comparison).data)

    @extend_schema(request=MergeSerializer, responses=ProductSerializer)
    @action(detail=True, methods=["post"])
    def merge(self, request, pk=None):
        """Merge other products into this one; they are deleted."""
        target = self.get_object()
        serializer = MergeSerializer(
            data=request.data, context={"household": self.household, "target": target}
        )
        serializer.is_valid(raise_exception=True)
        review_services.merge_products(target, serializer.validated_data["source_product_ids"])
        return Response(ProductSerializer(self.get_object()).data)


@extend_schema(tags=["review"])
class ReceiptItemViewSet(HouseholdScopedMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = ReceiptItem.objects.select_related("receipt__merchant", "product")
    serializer_class = ReviewItemSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    @extend_schema(responses=ReviewItemSerializer(many=True))
    @action(detail=False, methods=["get"])
    def review(self, request):
        """Product lines waiting for a person: not linked to a product (e.g. a reused code)."""
        items = (
            self.get_queryset()
            .filter(match_status=ReceiptItem.MatchStatus.NEEDS_REVIEW)
            .order_by("-receipt__issued_at", "line_number")
        )
        page = self.paginate_queryset(items)
        return self.get_paginated_response(ReviewItemSerializer(page, many=True).data)

    @extend_schema(request=ReceiptItemUpdateSerializer, responses=ReviewItemSerializer)
    def partial_update(self, request, *args, **kwargs):
        """Reclassify a line or change its note. Back to ``product``: it is matched again."""
        item = self.get_object()
        serializer = ReceiptItemUpdateSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        review_services.update_item(item, **serializer.validated_data)
        return Response(ReviewItemSerializer(self.get_object()).data)

    @extend_schema(request=MatchSerializer, responses=ReviewItemSerializer)
    @action(detail=True, methods=["post"])
    def match(self, request, pk=None):
        """Link the line to a product; the merchant's item is linked for future imports."""
        item = self.get_object()
        serializer = MatchSerializer(data=request.data, context={"household": self.household})
        serializer.is_valid(raise_exception=True)
        review_services.link_item(item, serializer.validated_data["product_id"])
        return Response(ReviewItemSerializer(self.get_object()).data)

    @extend_schema(request=ProductSerializer, responses={201: ReviewItemSerializer})
    @action(detail=True, methods=["post"], url_path="create-product")
    def create_product(self, request, pk=None):
        """Create a product from the line and link the line (and the merchant's item) to it."""
        item = self.get_object()
        serializer = ProductSerializer(data=request.data, context={"household": self.household})
        serializer.is_valid(raise_exception=True)
        review_services.create_product_for_item(item, **serializer.validated_data)
        return Response(
            ReviewItemSerializer(self.get_object()).data, status=status.HTTP_201_CREATED
        )


@extend_schema(tags=["categories"])
@extend_schema_view(
    partial_update=extend_schema(description="Household categories only (`403 system_category`)."),
    destroy=extend_schema(
        description="Household categories only. `409 category_in_use` while products use it."
    ),
)
class CategoryViewSet(
    HouseholdSerializerContextMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """System categories and the household's own (a flat list)."""

    queryset = ProductCategory.objects.all()
    serializer_class = CategorySerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def scope_queryset(self, queryset, household):
        return (
            queryset.filter(Q(household=household) | Q(household__isnull=True))
            .annotate(product_count=Count("products", filter=Q(products__household=household)))
            .order_by("name")
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = categories.create_category(self.household, **serializer.validated_data)
        return Response(self._read(category), status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        category = self.get_object()
        if category.is_system:  # before validation: the answer does not depend on the input
            raise SystemCategoryReadOnly()
        serializer = self.get_serializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data:
            categories.update_category(category, **serializer.validated_data)
        return Response(self._read(category))

    def perform_destroy(self, instance):
        categories.delete_category(instance)

    def _read(self, category) -> dict:
        return CategorySerializer(self.get_queryset().get(pk=category.pk)).data
