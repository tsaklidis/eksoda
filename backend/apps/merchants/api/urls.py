from django.urls import path

from apps.merchants.api import views

urlpatterns = [
    path("merchants", views.MerchantViewSet.as_view({"get": "list"}), name="merchants-list"),
    path(
        "merchants/<uuid:pk>",
        views.MerchantViewSet.as_view({"get": "retrieve"}),
        name="merchants-detail",
    ),
    path("stores", views.StoreViewSet.as_view({"get": "list"}), name="stores-list"),
]
