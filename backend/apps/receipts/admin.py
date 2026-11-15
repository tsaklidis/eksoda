"""Admin: the interim operations UI (D1). Import health is read here (D21).

Receipt URLs work as credentials, so the admin shows their fingerprints, never the
URLs themselves.
"""

from django.contrib import admin, messages

from apps.products.matching import rematch_receipt
from apps.products.prices import refresh_prices
from apps.receipts.api_errors import NotRetryable
from apps.receipts.models import Receipt, ReceiptImportJob, ReceiptItem
from apps.receipts.services.imports import retry_import


@admin.register(ReceiptImportJob)
class ReceiptImportJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "household",
        "provider_code",
        "status",
        "outcome",
        "last_error_code",
        "attempt_count",
        "next_attempt_at",
        "created_at",
    )
    list_filter = ("status", "provider_code", "last_error_code", "outcome")
    search_fields = ("id", "household__name", "issuer_vat", "url_fingerprint")
    list_select_related = ("household",)
    exclude = ("submitted_url",)
    readonly_fields = (
        "id",
        "household",
        "requested_by",
        "provider_code",
        "url_identity",
        "url_fingerprint",
        "issuer_vat",
        "status",
        "outcome",
        "attempt_count",
        "next_attempt_at",
        "last_error_code",
        "last_error_message",
        "receipt",
        "finished_at",
        "created_at",
        "updated_at",
    )
    actions = ("retry_imports",)

    def has_add_permission(self, request) -> bool:
        return False  # jobs are created by submitting a link through the API

    @admin.action(description="Retry the selected failed imports")
    def retry_imports(self, request, queryset):
        retried = skipped = 0
        for job in queryset:
            try:
                retry_import(job)
                retried += 1
            except NotRetryable:
                skipped += 1
        self.message_user(request, f"Retried {retried} import(s).", messages.SUCCESS)
        if skipped:
            self.message_user(
                request, f"Skipped {skipped} import(s) that have not failed.", messages.WARNING
            )


class ReceiptItemInline(admin.TabularInline):
    model = ReceiptItem
    extra = 0
    can_delete = False
    fields = (
        "line_number",
        "line_type",
        "description",
        "merchant_product_code",
        "quantity",
        "unit",
        "unit_price",
        "gross_amount",
        "vat_rate",
        "discount_amount",
        "match_status",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "issued_at",
        "merchant",
        "store",
        "gross_total",
        "currency",
        "document_kind",
        "status",
        "provider_code",
        "household",
    )
    list_filter = ("provider_code", "parser_version", "document_kind", "status", "payment_method")
    search_fields = (
        "document_number",
        "mark",
        "uid",
        "source_key",
        "merchant__display_name",
        "merchant__vat_number",
        "household__name",
    )
    list_select_related = ("merchant", "store", "household")
    date_hierarchy = "issued_at"
    exclude = ("source_url",)
    readonly_fields = (
        "id",
        "household",
        "imported_by",
        "merchant",
        "store",
        "provider_code",
        "parser_version",
        "issuer_country",
        "issuer_vat",
        "uid",
        "mark",
        "cancellation_mark",
        "source_key",
        "document_kind",
        "document_type_code",
        "document_number",
        "issued_at",
        "currency",
        "gross_total",
        "net_total",
        "vat_total",
        "discount_total",
        "payment_method",
        "status",
        "validation_warnings",
        "source_url_fingerprint",
        "source_data",
        "created_at",
        "updated_at",
    )
    inlines = (ReceiptItemInline,)
    actions = ("rematch", "recompute_prices")

    def has_add_permission(self, request) -> bool:
        return False  # receipts come from imports only

    @admin.action(description="Match the unmatched product lines of the selected receipts")
    def rematch(self, request, queryset):
        matched = sum(rematch_receipt(receipt) for receipt in queryset.order_by("issued_at"))
        self.message_user(request, f"Matched {matched} line(s).", messages.SUCCESS)

    @admin.action(description="Recompute the line prices of the selected receipts")
    def recompute_prices(self, request, queryset):
        items = ReceiptItem.objects.filter(receipt__in=queryset).select_related("product")
        refresh_prices(items)
        self.message_user(request, "Prices recomputed.", messages.SUCCESS)


@admin.register(ReceiptItem)
class ReceiptItemAdmin(admin.ModelAdmin):
    """Read-only apart from the note: reclassify and link lines through the API, which
    keeps products, mappings and prices consistent."""

    list_display = (
        "description",
        "receipt",
        "line_type",
        "match_status",
        "product",
        "quantity",
        "unit",
        "gross_amount",
        "normalized_unit_price",
        "normalized_unit",
    )
    list_filter = ("line_type", "match_status", "unit", "normalized_unit")
    search_fields = ("description", "normalized_description", "merchant_product_code")
    list_select_related = ("receipt", "product")
    readonly_fields = tuple(
        field.name for field in ReceiptItem._meta.fields if field.name != "user_note"
    )

    def has_add_permission(self, request) -> bool:
        return False
