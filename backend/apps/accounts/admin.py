from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import BaseUserCreationForm

from apps.accounts.models import User


class UserCreationForm(BaseUserCreationForm):
    """Django's creation form (password match and validators) for the email-login user."""

    class Meta:
        model = User
        fields = ("email", "display_name")

    def clean_email(self) -> str:
        # Checked here, case-insensitively, so a taken email is reported on the field
        # instead of as a generic violation of the Lower(email) constraint.
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # The change form is Django's UserChangeForm; the admin binds it to this model.
    add_form = UserCreationForm
    list_display = ("email", "display_name", "is_staff", "is_active", "created_at")
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("email", "display_name")
    ordering = ("email",)
    readonly_fields = ("last_login", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("display_name",)}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {"classes": ("wide",), "fields": ("email", "display_name", "password1", "password2")},
        ),
    )
