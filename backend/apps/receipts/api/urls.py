from django.urls import path

from apps.receipts.api import views

receipt_list = views.ReceiptViewSet.as_view({"get": "list"})
receipt_detail = views.ReceiptViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
)
import_list = views.ImportJobViewSet.as_view({"get": "list"})
import_detail = views.ImportJobViewSet.as_view({"get": "retrieve"})
import_retry = views.ImportJobViewSet.as_view({"post": "retry"})

urlpatterns = [
    path("receipts/import", views.ReceiptImportView.as_view(), name="receipts-import"),
    path("receipts", receipt_list, name="receipts-list"),
    path("receipts/<uuid:pk>", receipt_detail, name="receipts-detail"),
    path("receipt-imports", import_list, name="receipt-imports-list"),
    path("receipt-imports/<uuid:pk>", import_detail, name="receipt-imports-detail"),
    path("receipt-imports/<uuid:pk>/retry", import_retry, name="receipt-imports-retry"),
]
