from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.households.models import HouseholdInvitation, HouseholdMember
from apps.households.services import create_invitation
from tests.factories import DEFAULT_PASSWORD, UserFactory
from tests.utils import error_code

pytestmark = pytest.mark.django_db
URL = reverse("api-v1:auth-register")


def payload(**overrides):
    return {"email": "New.Person@Example.com", "password": DEFAULT_PASSWORD, **overrides}


def test_closed_registration_requires_an_invite(api_client):
    response = api_client.post(URL, payload(), format="json")
    assert response.status_code == 400
    assert error_code(response) == "invite_required"
    assert not User.objects.exists()


def test_open_registration_creates_personal_household(api_client, settings):
    settings.REGISTRATION_OPEN = True
    response = api_client.post(URL, payload(display_name="Maria"), format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "new.person@example.com"
    assert body["user"]["memberships"][0]["household_name"] == "Maria's household"
    assert body["user"]["memberships"][0]["role"] == "owner"
    assert set(body["tokens"]) == {"access", "refresh"}

    me = api_client.get(
        reverse("api-v1:auth-me"), HTTP_AUTHORIZATION=f"Bearer {body['tokens']['access']}"
    )
    assert me.status_code == 200


def test_open_registration_names_household_after_email_without_display_name(api_client, settings):
    settings.REGISTRATION_OPEN = True
    response = api_client.post(URL, payload(), format="json")
    assert response.json()["user"]["memberships"][0]["household_name"] == "new.person's household"


def test_registration_with_invite_joins_that_household(api_client, owner):
    invitation, code = create_invitation(household=owner.household, created_by=owner.user)
    response = api_client.post(URL, payload(invite_code=code), format="json")

    assert response.status_code == 201
    user = User.objects.get(email="new.person@example.com")
    membership = HouseholdMember.objects.get(user=user)
    assert membership.household == owner.household
    assert membership.role == HouseholdMember.Role.MEMBER
    invitation.refresh_from_db()
    assert invitation.status == HouseholdInvitation.Status.ACCEPTED
    assert invitation.accepted_by == user


@pytest.mark.parametrize("state", ["unknown", "expired", "revoked", "used"])
def test_unusable_invites_create_no_user(api_client, owner, state):
    invitation, code = create_invitation(household=owner.household, created_by=owner.user)
    if state == "unknown":
        code = "not-a-real-code"
    elif state == "expired":
        invitation.expires_at = timezone.now() - timedelta(seconds=1)
    elif state == "revoked":
        invitation.revoked_at = timezone.now()
    elif state == "used":
        invitation.accepted_at = timezone.now()
    invitation.save()
    users_before = User.objects.count()

    response = api_client.post(URL, payload(invite_code=code), format="json")

    assert response.status_code == 400
    assert error_code(response) == "invalid_invitation"
    assert User.objects.count() == users_before


def test_duplicate_email_is_rejected_case_insensitively(api_client, settings):
    settings.REGISTRATION_OPEN = True
    UserFactory(email="new.person@example.com")
    response = api_client.post(URL, payload(), format="json")
    assert response.status_code == 400
    assert "email" in response.json()["error"]["details"]


def test_weak_password_is_rejected(api_client, settings):
    settings.REGISTRATION_OPEN = True
    response = api_client.post(URL, payload(password="password"), format="json")
    assert response.status_code == 400
    assert "password" in response.json()["error"]["details"]


def test_registration_is_rate_limited(api_client):
    for _ in range(10):
        assert api_client.post(URL, {}, format="json").status_code == 400
    response = api_client.post(URL, {}, format="json")
    assert response.status_code == 429
    assert error_code(response) == "rate_limited"


def test_concurrent_duplicate_email_is_a_400(settings):
    from rest_framework.exceptions import ValidationError

    from apps.accounts.services import register_user

    settings.REGISTRATION_OPEN = True
    UserFactory(email="race@example.com")
    with pytest.raises(ValidationError):  # the serializer check was passed by both requests
        register_user(email="race@example.com", password=DEFAULT_PASSWORD)
