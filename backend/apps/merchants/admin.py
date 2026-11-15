from django.contrib import admin

from apps.merchants.models import Merchant, Store


class StoreInline(admin.TabularInline):
    model = Store
    extra = 0
    fields = ("branch_number", "display_name", "street", "city", "postal_code")
    show_change_link = True


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    """Merchants are created by imports; staff curate the display name and details."""

    list_display = (
        "display_name",
        "legal_name",
        "vat_number",
        "city",
        "default_category",
        "updated_at",
    )
    list_filter = ("country_code", "default_category")
    search_fields = ("display_name", "legal_name", "vat_number")
    readonly_fields = ("id", "details_as_of", "created_at", "updated_at")
    inlines = (StoreInline,)


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("label", "merchant", "branch_number", "city", "postal_code")
    list_filter = ("merchant__country_code",)
    search_fields = (
        "display_name",
        "street",
        "city",
        "postal_code",
        "branch_number",
        "merchant__display_name",
        "merchant__vat_number",
    )
    autocomplete_fields = ("merchant",)
    readonly_fields = ("id", "normalized_address", "details_as_of", "created_at", "updated_at")
