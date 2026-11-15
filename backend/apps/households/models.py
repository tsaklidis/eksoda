"""Households own all purchase data (requirements §5, TD §7.1)."""

import re
import zoneinfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.common.models import UUIDModel

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def validate_timezone(value: str) -> None:
    if value not in zoneinfo.available_timezones():
        raise ValidationError(f"{value!r} is not a valid IANA timezone.", code="invalid_timezone")


def validate_currency(value: str) -> None:
    if not _CURRENCY_RE.match(value):
        raise ValidationError("Currency must be a 3-letter ISO 4217 code.", code="invalid_currency")


class Household(UUIDModel):
    name = models.CharField(max_length=120)
    default_currency = models.CharField(max_length=3, default="EUR", validators=[validate_currency])
    timezone = models.CharField(
        max_length=64, default="Europe/Athens", validators=[validate_timezone]
    )

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class HouseholdMember(UUIDModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MEMBER = "member", "Member"

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["household", "user"], name="uniq_household_member"),
        ]
        ordering = ("joined_at",)

    def __str__(self) -> str:
        return f"{self.user} in {self.household} ({self.role})"


class HouseholdInvitation(UUIDModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="invitations")
    code_hash = models.CharField(max_length=64, unique=True)  # sha256 of the code
    role = models.CharField(
        max_length=10, choices=HouseholdMember.Role.choices, default=HouseholdMember.Role.MEMBER
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    expires_at = models.DateTimeField()
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Invitation to {self.household} ({self.status})"

    @property
    def status(self) -> str:
        if self.revoked_at:
            return self.Status.REVOKED
        if self.accepted_at:
            return self.Status.ACCEPTED
        if self.expires_at <= timezone.now():
            return self.Status.EXPIRED
        return self.Status.PENDING
