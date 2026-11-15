from django.urls import path

from apps.products.api import views

products = views.ProductViewSet.as_view({"get": "list", "post": "create"})
product = views.ProductViewSet.as_view({"get": "retrieve", "patch": "partial_update"})
items = views.ReceiptItemViewSet

urlpatterns = [
    path("products", products, name="products-list"),
    path("products/<uuid:pk>", product, name="products-detail"),
    path(
        "products/<uuid:pk>/prices",
        views.ProductViewSet.as_view({"get": "prices"}),
        name="products-prices",
    ),
    path(
        "products/<uuid:pk>/price-comparison",
        views.ProductViewSet.as_view({"get": "price_comparison"}),
        name="products-price-comparison",
    ),
    path(
        "products/<uuid:pk>/merge",
        views.ProductViewSet.as_view({"post": "merge"}),
        name="products-merge",
    ),
    path("receipt-items/review", items.as_view({"get": "review"}), name="receipt-items-review"),
    path(
        "receipt-items/<uuid:pk>",
        items.as_view({"patch": "partial_update"}),
        name="receipt-items-detail",
    ),
    path(
        "receipt-items/<uuid:pk>/match",
        items.as_view({"post": "match"}),
        name="receipt-items-match",
    ),
    path(
        "receipt-items/<uuid:pk>/create-product",
        items.as_view({"post": "create_product"}),
        name="receipt-items-create-product",
    ),
]

categories = views.CategoryViewSet
urlpatterns += [
    path(
        "categories",
        categories.as_view({"get": "list", "post": "create"}),
        name="categories-list",
    ),
    path(
        "categories/<uuid:pk>",
        categories.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="categories-detail",
    ),
]
