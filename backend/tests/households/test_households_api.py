import pytest
from django.urls import reverse

from apps.households.models import HouseholdMember
from tests.factories import MemberFactory
from tests.utils import error_code

pytestmark = pytest.mark.django_db


def detail_url(household_id):
    return reverse("api-v1:households-detail", kwargs={"pk": household_id})


def members_url(household_id):
    return reverse("api-v1:household-members", kwargs={"household_id": household_id})


def member_url(household_id, member_id):
    return reverse(
        "api-v1:household-member-detail",
        kwargs={"household_id": household_id, "member_id": member_id},
    )


def test_list_shows_only_own_households_with_role(owner, member, outsider, member_client):
    response = member_client.get(reverse("api-v1:households-list"))
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(owner.household_id),
            "name": owner.household.name,
            "default_currency": "EUR",
            "timezone": "Europe/Athens",
            "role": "member",
            "created_at": response.json()[0]["created_at"],
        }
    ]


def test_detail_of_foreign_household_is_404(owner_client, outsider):
    response = owner_client.get(detail_url(outsider.household_id))
    assert response.status_code == 404
    assert error_code(response) == "not_found"


def test_owner_updates_settings(owner, owner_client):
    response = owner_client.patch(
        detail_url(owner.household_id),
        {"name": "Our home", "timezone": "Europe/Berlin", "default_currency": "usd"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Our home"
    assert response.json()["default_currency"] == "USD"
    assert response.json()["role"] == "owner"
    owner.household.refresh_from_db()
    assert owner.household.timezone == "Europe/Berlin"


@pytest.mark.parametrize("field", [{"timezone": "Mars/Base"}, {"default_currency": "EURO"}])
def test_invalid_settings_are_rejected(owner, owner_client, field):
    response = owner_client.patch(detail_url(owner.household_id), field, format="json")
    assert response.status_code == 400
    assert set(field) <= set(response.json()["error"]["details"])


def test_members_cannot_update_settings(owner, member_client):
    response = member_client.patch(
        detail_url(owner.household_id), {"timezone": "invalid"}, format="json"
    )
    assert response.status_code == 403
    assert error_code(response) == "owner_required"


def test_put_is_not_allowed(owner, owner_client):
    response = owner_client.put(detail_url(owner.household_id), {"name": "x"}, format="json")
    assert response.status_code == 405


def test_members_list(owner, member, member_client):
    response = member_client.get(members_url(owner.household_id))
    assert response.status_code == 200
    assert [(row["email"], row["role"]) for row in response.json()] == [
        (owner.user.email, "owner"),
        (member.user.email, "member"),
    ]


def test_owner_removes_member(owner, member, owner_client):
    response = owner_client.delete(member_url(owner.household_id, member.pk))
    assert response.status_code == 204
    assert not HouseholdMember.objects.filter(pk=member.pk).exists()


def test_member_can_leave(owner, member, member_client):
    assert member_client.delete(member_url(owner.household_id, member.pk)).status_code == 204


def test_member_cannot_remove_others(owner, member, member_client):
    response = member_client.delete(member_url(owner.household_id, owner.pk))
    assert response.status_code == 403
    assert error_code(response) == "owner_required"


def test_last_owner_cannot_leave(owner, owner_client):
    response = owner_client.delete(member_url(owner.household_id, owner.pk))
    assert response.status_code == 409
    assert error_code(response) == "last_owner"


def test_owner_can_leave_when_another_owner_remains(owner, owner_client):
    MemberFactory(household=owner.household, role=HouseholdMember.Role.OWNER)
    assert owner_client.delete(member_url(owner.household_id, owner.pk)).status_code == 204


def test_unknown_member_is_404(owner, outsider, owner_client):
    response = owner_client.delete(member_url(owner.household_id, outsider.pk))
    assert response.status_code == 404
