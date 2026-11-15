from django.contrib import admin

from apps.households.models import Household, HouseholdInvitation, HouseholdMember


class HouseholdMemberInline(admin.TabularInline):
    model = HouseholdMember
    extra = 0
    autocomplete_fields = ("user",)
    readonly_fields = ("joined_at",)


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ("name", "default_currency", "timezone", "created_at")
    search_fields = ("name",)
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = (HouseholdMemberInline,)


@admin.register(HouseholdInvitation)
class HouseholdInvitationAdmin(admin.ModelAdmin):
    list_display = ("household", "role", "status", "expires_at", "accepted_by", "created_at")
    list_filter = ("role",)
    search_fields = ("household__name",)
    readonly_fields = (
        "id",
        "code_hash",
        "created_by",
        "accepted_by",
        "accepted_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:
        return False  # codes are created through the API so they can be shown once
