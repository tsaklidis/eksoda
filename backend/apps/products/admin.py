from django.contrib import admin, messages

from apps.products.models import MerchantProductMapping, Product, ProductCategory
from apps.products.prices import refresh_product_prices


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "household")
    list_filter = (("household", admin.EmptyFieldListFilter),)
    search_fields = ("name", "slug", "household__name")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("id", "created_at", "updated_at")


class MappingInline(admin.TabularInline):
    model = MerchantProductMapping
    extra = 0
    fields = ("merchant", "merchant_product_code", "last_seen_description")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "household",
        "brand",
        "category",
        "package_quantity",
        "package_unit",
        "updated_at",
    )
    list_filter = ("category", "package_unit")
    search_fields = ("name", "normalized_name", "brand", "household__name")
    list_select_related = ("household", "category")
    readonly_fields = ("id", "household", "normalized_name", "created_at", "updated_at")
    inlines = (MappingInline,)
    actions = ("recompute_prices",)

    def has_add_permission(self, request) -> bool:
        return False  # products belong to a household: created by imports or its members

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and {"package_quantity", "package_unit"} & set(form.changed_data):
            refresh_product_prices(obj)

    @admin.action(description="Recompute the line prices of the selected products")
    def recompute_prices(self, request, queryset):
        for product in queryset:
            refresh_product_prices(product)
        self.message_user(request, f"Recomputed {queryset.count()} product(s).", messages.SUCCESS)


@admin.register(MerchantProductMapping)
class MerchantProductMappingAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "merchant",
        "merchant_product_code",
        "last_seen_description",
        "household",
    )
    search_fields = (
        "merchant_product_code",
        "normalized_description",
        "product__name",
        "merchant__display_name",
    )
    list_select_related = ("product", "merchant", "household")
    readonly_fields = (
        "id",
        "household",
        "merchant",
        "merchant_product_code",
        "normalized_description",
        "last_seen_description",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("product",)

    def has_add_permission(self, request) -> bool:
        return False
