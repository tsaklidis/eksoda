from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.households.models import HouseholdInvitation, HouseholdMember
from apps.households.services import create_invitation, hash_invitation_code
from tests.utils import client_for, error_code

pytestmark = pytest.mark.django_db
JOIN = reverse("api-v1:households-join")


def invitations_url(household_id):
    return reverse("api-v1:household-invitations", kwargs={"household_id": household_id})


def invitation_url(household_id, invitation_id):
    return reverse(
        "api-v1:household-invitation-detail",
        kwargs={"household_id": household_id, "invitation_id": invitation_id},
    )


def test_owner_creates_invitation_and_code_is_shown_once(owner, owner_client):
    response = owner_client.post(invitations_url(owner.household_id), {}, format="json")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["role"] == "member"
    assert body["created_by_email"] == owner.user.email

    stored = HouseholdInvitation.objects.get(pk=body["id"])
    assert stored.code_hash == hash_invitation_code(body["code"])
    assert stored.code_hash != body["code"]

    listing = owner_client.get(invitations_url(owner.household_id)).json()
    assert [row["id"] for row in listing] == [body["id"]]
    assert "code" not in listing[0]


def test_owner_can_invite_another_owner(owner, owner_client):
    response = owner_client.post(
        invitations_url(owner.household_id), {"role": "owner"}, format="json"
    )
    assert response.json()["role"] == "owner"


def test_members_cannot_manage_invitations(owner, member_client):
    assert member_client.get(invitations_url(owner.household_id)).status_code == 403
    response = member_client.post(invitations_url(owner.household_id), {}, format="json")
    assert response.status_code == 403
    assert error_code(response) == "owner_required"


def test_revoke_pending_invitation_only_once(owner, owner_client):
    invitation, _ = create_invitation(household=owner.household, created_by=owner.user)
    url = invitation_url(owner.household_id, invitation.pk)
    assert owner_client.delete(url).status_code == 204
    invitation.refresh_from_db()
    assert invitation.status == HouseholdInvitation.Status.REVOKED

    response = owner_client.delete(url)
    assert response.status_code == 409
    assert error_code(response) == "invitation_not_pending"


def test_join_with_code(owner, outsider, outsider_client):
    invitation, code = create_invitation(household=owner.household, created_by=owner.user)
    response = outsider_client.post(JOIN, {"code": f"  {code} "}, format="json")

    assert response.status_code == 201
    assert response.json()["role"] == "member"
    assert HouseholdMember.objects.filter(household=owner.household, user=outsider.user).exists()
    invitation.refresh_from_db()
    assert invitation.status == HouseholdInvitation.Status.ACCEPTED

    again = outsider_client.post(JOIN, {"code": code}, format="json")
    assert again.status_code == 400
    assert error_code(again) == "invalid_invitation"


def test_existing_member_cannot_consume_an_invitation(owner, member_client):
    invitation, code = create_invitation(household=owner.household, created_by=owner.user)
    response = member_client.post(JOIN, {"code": code}, format="json")
    assert response.status_code == 409
    assert error_code(response) == "already_member"
    invitation.refresh_from_db()
    assert invitation.status == HouseholdInvitation.Status.PENDING


@pytest.mark.parametrize("state", ["expired", "revoked"])
def test_join_with_unusable_code(owner, outsider_client, state):
    invitation, code = create_invitation(household=owner.household, created_by=owner.user)
    if state == "expired":
        invitation.expires_at = timezone.now() - timedelta(minutes=1)
    else:
        invitation.revoked_at = timezone.now()
    invitation.save()
    response = outsider_client.post(JOIN, {"code": code}, format="json")
    assert response.status_code == 400
    assert error_code(response) == "invalid_invitation"


def test_join_is_rate_limited(outsider):
    client = client_for(outsider.user)
    for _ in range(20):
        client.post(JOIN, {"code": "nope"}, format="json")
    response = client.post(JOIN, {"code": "nope"}, format="json")
    assert response.status_code == 429


def test_concurrent_join_maps_the_race_to_already_member(owner, member, monkeypatch):
    from django.db.models import QuerySet

    from apps.households.errors import AlreadyMember
    from apps.households.services import accept_invitation

    _invitation, code = create_invitation(household=owner.household, created_by=owner.user)
    monkeypatch.setattr(QuerySet, "exists", lambda self: False)  # the other request won
    with pytest.raises(AlreadyMember):
        accept_invitation(code=code, user=member.user)
