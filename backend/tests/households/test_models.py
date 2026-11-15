from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.households.models import (
    HouseholdInvitation,
    validate_currency,
    validate_timezone,
)
from apps.households.services import create_invitation

pytestmark = pytest.mark.django_db


def test_validators():
    validate_timezone("Europe/Athens")
    validate_currency("EUR")
    with pytest.raises(ValidationError):
        validate_timezone("Nowhere/City")
    with pytest.raises(ValidationError):
        validate_currency("eur")


def test_invitation_status_precedence(owner):
    invitation, _ = create_invitation(household=owner.household, created_by=owner.user)
    assert invitation.status == HouseholdInvitation.Status.PENDING
    invitation.expires_at = timezone.now() - timedelta(seconds=1)
    assert invitation.status == HouseholdInvitation.Status.EXPIRED
    invitation.accepted_at = timezone.now()
    assert invitation.status == HouseholdInvitation.Status.ACCEPTED
    invitation.revoked_at = timezone.now()
    assert invitation.status == HouseholdInvitation.Status.REVOKED


def test_string_representations(owner):
    invitation, _ = create_invitation(household=owner.household, created_by=owner.user)
    assert str(owner.household) == owner.household.name
    assert owner.household.name in str(owner)
    assert "pending" in str(invitation)
