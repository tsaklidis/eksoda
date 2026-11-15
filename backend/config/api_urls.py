"""All routes under /api/v1/ (namespace "api-v1"). Paths have no trailing slash."""

from django.urls import include, path

urlpatterns = [
    path("", include("apps.accounts.api.urls")),
    path("", include("apps.households.api.urls")),
    path("", include("apps.receipts.api.urls")),
    path("", include("apps.products.api.urls")),
    path("", include("apps.merchants.api.urls")),
    path("analytics/", include("apps.analytics.api.urls")),
]
