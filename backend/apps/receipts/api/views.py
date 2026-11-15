"""Receipt import and receipt endpoints (requirements §6.2, §12.4, §12.5).

All of them are household-scoped through the X-Household-ID header: objects of
other households answer 404.
"""

from django.db.models import Count, Exists, OuterRef, Prefetch
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.common.households import HouseholdScopedMixin
from apps.common.parsers import LimitedJSONParser
from apps.receipts.api.filters import ImportJobFilter, ReceiptFilter
from apps.receipts.api.serializers import (
    ImportJobSerializer,
    ImportRequestSerializer,
    ImportSubmitResponseSerializer,
    ReceiptDetailSerializer,
    ReceiptListSerializer,
    ReceiptUpdateSerializer,
)
from apps.receipts.api_errors import SUBMISSION_ERRORS, for_submission_error
from apps.receipts.models import Receipt, ReceiptImportJob, ReceiptItem
from apps.receipts.services import imports
from apps.receipts.services import receipts as receipt_services


class ImportMinuteThrottle(UserRateThrottle):
    scope = "import_minute"


class ImportDayThrottle(UserRateThrottle):
    scope = "import_day"


class SmallJSONParser(LimitedJSONParser):
    """JSON with a small body limit (requirements §6.2: at most 4 KB)."""

    max_bytes = 4 * 1024


@extend_schema(tags=["imports"])
class ReceiptImportView(HouseholdScopedMixin, APIView):
    """Submit a receipt link. Importing happens in the background."""

    parser_classes = [SmallJSONParser]
    throttle_classes = [ImportMinuteThrottle, ImportDayThrottle]

    @extend_schema(
        request=ImportRequestSerializer,
        responses={
            202: OpenApiResponse(
                ImportSubmitResponseSerializer, description="New, or started again (failed before)."
            ),
            200: OpenApiResponse(
                ImportSubmitResponseSerializer,
                description="Already submitted: the existing import.",
            ),
        },
        description=(
            "Errors: `invalid_request` (malformed JSON or too large), `invalid_url`, "
            "`unsupported_provider` (422), `unsupported_url_format` (422), `rate_limited` (429)."
        ),
    )
    def post(self, request):
        serializer = ImportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = imports.submit_import(
                user=request.user,
                household=self.household,
                raw_url=serializer.validated_data["url"],
            )
        except SUBMISSION_ERRORS as exc:
            raise for_submission_error(exc) from None
        job = result.job
        job.duplicate = not result.created  # read by ImportSubmitResponseSerializer
        started = result.created or result.requeued
        return Response(
            ImportSubmitResponseSerializer(job).data,
            status=status.HTTP_202_ACCEPTED if started else status.HTTP_200_OK,
        )


@extend_schema(tags=["imports"])
class ImportJobViewSet(HouseholdScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ReceiptImportJob.objects.all()
    serializer_class = ImportJobSerializer
    filterset_class = ImportJobFilter
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    @extend_schema(
        request=None,
        responses={202: ImportJobSerializer},
        description="Start a failed import again with the full retry schedule. "
        "`409 not_retryable` unless the import has failed.",
    )
    def get_throttles(self):
        # A retry fetches the receipt page again: it counts against the import limits.
        if self.action == "retry":
            return [ImportMinuteThrottle(), ImportDayThrottle()]
        return super().get_throttles()

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        job = imports.retry_import(self.get_object())
        return Response(ImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


@extend_schema(tags=["receipts"])
@extend_schema_view(
    partial_update=extend_schema(
        request=ReceiptUpdateSerializer, responses={200: ReceiptDetailSerializer}
    ),
)
class ReceiptViewSet(
    HouseholdScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Receipt.objects.all()
    filterset_class = ReceiptFilter
    ordering_fields = ["issued_at", "gross_total"]
    ordering = ["-issued_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return ReceiptListSerializer
        if self.action == "partial_update":
            return ReceiptUpdateSerializer
        return ReceiptDetailSerializer

    def get_queryset(self):
        needs_review = ReceiptItem.objects.filter(
            receipt=OuterRef("pk"), match_status=ReceiptItem.MatchStatus.NEEDS_REVIEW
        )
        queryset = (
            super()
            .get_queryset()
            .select_related("merchant", "store")
            .annotate(item_count=Count("items"), needs_review=Exists(needs_review))
        )
        if self.action != "list":
            queryset = queryset.prefetch_related(
                Prefetch(
                    "items",
                    queryset=ReceiptItem.objects.select_related("product").order_by("line_number"),
                )
            )
        return queryset

    def update(self, request, *args, **kwargs):
        # PATCH only (urls.py routes no PUT). The answer is the full receipt, read
        # again so its annotations and lines are current.
        receipt = self.get_object()
        serializer = ReceiptUpdateSerializer(receipt, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        receipt_services.update_receipt(receipt, **serializer.validated_data)
        return Response(ReceiptDetailSerializer(self.get_object()).data)

    def perform_destroy(self, instance):
        receipt_services.delete_receipt(instance)
