from django.urls import path

from apps.analytics.api import views

urlpatterns = [
    path("summary", views.SummaryView.as_view(), name="analytics-summary"),
    path(
        "spending-by-category",
        views.SpendingByCategoryView.as_view(),
        name="analytics-spending-by-category",
    ),
    path(
        "spending-by-merchant",
        views.SpendingByMerchantView.as_view(),
        name="analytics-spending-by-merchant",
    ),
    path("monthly-trend", views.MonthlyTrendView.as_view(), name="analytics-monthly-trend"),
    path("top-products", views.TopProductsView.as_view(), name="analytics-top-products"),
]
