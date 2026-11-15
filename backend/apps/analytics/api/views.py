"""Spending analytics endpoints (requirements §12.9, §13). Household-scoped, read-only.

Periods are inclusive dates in the household timezone. Without ``from`` and ``to``
the period is the current month; ``from`` alone runs to today; ``to`` alone starts
on the first day of its month.
"""

from datetime import date
from decimal import Decimal

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics import queries
from apps.analytics.api.serializers import (
    CategorySpendingSerializer,
    MerchantSpendingSerializer,
    PeriodQuerySerializer,
    SummarySerializer,
    TopProductsQuerySerializer,
    TopProductsSerializer,
    TrendQuerySerializer,
    TrendSerializer,
)
from apps.analytics.periods import Period, month_period, month_start, months_ending
from apps.common.households import HouseholdScopedMixin

DEFAULT_TREND_MONTHS = 12
DEFAULT_TOP_LIMIT = 10

FROM = OpenApiParameter("from", OpenApiTypes.DATE, description="First day, inclusive.")
TO = OpenApiParameter("to", OpenApiTypes.DATE, description="Last day, inclusive.")
PERIOD = [FROM, TO]


class AnalyticsView(HouseholdScopedMixin, APIView):
    def validated(self, serializer_class) -> dict:
        serializer = serializer_class(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def period(self, params: dict) -> Period:
        today = timezone.localdate()  # the household timezone is active
        first, last = params.get("from"), params.get("to")
        if first is None and last is None:
            return month_period(today)
        if last is None:
            return Period(first, max(first, today))
        return Period(first or month_start(last), last)

    def answer(self, serializer_class, period: Period, **data) -> Response:
        payload = {"period": period, "currency": self.household.default_currency, **data}
        return Response(serializer_class(payload).data)


@extend_schema(tags=["analytics"], parameters=PERIOD, responses=SummarySerializer)
class SummaryView(AnalyticsView):
    """Spending, receipt counts and the change from the previous period of equal length."""

    def get(self, request):
        period = self.period(self.validated(PeriodQuerySerializer))
        return Response(SummarySerializer(queries.summary(self.household, period)).data)


@extend_schema(tags=["analytics"], parameters=PERIOD, responses=CategorySpendingSerializer)
class SpendingByCategoryView(AnalyticsView):
    """Spending per category. The buckets always add up to the total."""

    def get(self, request):
        period = self.period(self.validated(PeriodQuerySerializer))
        breakdown = queries.spending_by_category(self.household, period)
        return self.answer(
            CategorySpendingSerializer, period, total=breakdown.spending, buckets=breakdown.buckets
        )


@extend_schema(tags=["analytics"], parameters=PERIOD, responses=MerchantSpendingSerializer)
class SpendingByMerchantView(AnalyticsView):
    def get(self, request):
        period = self.period(self.validated(PeriodQuerySerializer))
        rows = queries.spending_by_merchant(self.household, period)
        total = sum((row["total"] for row in rows), Decimal("0.00"))
        return self.answer(MerchantSpendingSerializer, period, total=total, merchants=rows)


@extend_schema(
    tags=["analytics"],
    parameters=[
        OpenApiParameter("to", OpenApiTypes.DATE, description="A day in the last month."),
        OpenApiParameter("months", OpenApiTypes.INT, description="1–36, default 12."),
    ],
    responses=TrendSerializer,
)
class MonthlyTrendView(AnalyticsView):
    """Spending per calendar month; months without receipts are 0."""

    def get(self, request):
        params = self.validated(TrendQuerySerializer)
        last_day: date = params.get("to") or timezone.localdate()
        period = months_ending(last_day, params.get("months", DEFAULT_TREND_MONTHS))
        months = queries.monthly_trend(self.household, period)
        return self.answer(TrendSerializer, period, months=months)


@extend_schema(
    tags=["analytics"],
    parameters=[
        *PERIOD,
        OpenApiParameter(
            "by", OpenApiTypes.STR, enum=["count", "spend"], description="Default count."
        ),
        OpenApiParameter("limit", OpenApiTypes.INT, description="1–50, default 10."),
    ],
    responses=TopProductsSerializer,
)
class TopProductsView(AnalyticsView):
    """Products bought on the most receipts, or with the highest spend."""

    def get(self, request):
        params = self.validated(TopProductsQuerySerializer)
        period, by = self.period(params), params.get("by", "count")
        products = queries.top_products(
            self.household, period, by=by, limit=params.get("limit", DEFAULT_TOP_LIMIT)
        )
        return self.answer(TopProductsSerializer, period, by=by, products=products)
