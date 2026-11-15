import uuid

import pytest
from django.conf import settings
from django.utils import timezone

from apps.households.models import HouseholdMember
from tests.factories import MemberFactory
from tests.utils import client_for, error_code

pytestmark = [pytest.mark.django_db, pytest.mark.urls("tests.common.urls")]


def test_single_membership_is_used_without_header(owner, owner_client):
    response = owner_client.get("/ctx")
    assert response.status_code == 200
    assert response.json() == {
        "household_id": str(owner.household_id),
        "timezone": "Europe/Athens",
    }


def test_household_timezone_is_activated_and_reset(owner, member_client):
    owner.household.timezone = "America/New_York"
    owner.household.save()
    response = member_client.get("/ctx")
    assert response.json()["timezone"] == "America/New_York"
    assert timezone.get_current_timezone_name() == settings.TIME_ZONE


def test_several_memberships_require_the_header(owner, outsider):
    MemberFactory(household=outsider.household, user=owner.user, role="member")
    client = client_for(owner.user)

    response = client.get("/ctx")
    assert response.status_code == 400
    assert error_code(response) == "household_required"

    response = client.get("/ctx", HTTP_X_HOUSEHOLD_ID=str(outsider.household_id))
    assert response.status_code == 200
    assert response.json()["household_id"] == str(outsider.household_id)


@pytest.mark.parametrize(
    "header",
    ["foreign", str(uuid.uuid4()), "not-a-uuid"],
    ids=["foreign-household", "unknown-household", "malformed"],
)
def test_inaccessible_households_all_get_the_same_403(owner_client, outsider, header):
    value = str(outsider.household_id) if header == "foreign" else header
    response = owner_client.get("/ctx", HTTP_X_HOUSEHOLD_ID=value)
    assert response.status_code == 403
    assert error_code(response) == "household_forbidden"


def test_user_without_household_gets_403(db):
    user = MemberFactory().user
    HouseholdMember.objects.filter(user=user).delete()
    response = client_for(user).get("/ctx")
    assert response.status_code == 403
    assert error_code(response) == "household_forbidden"


def test_unauthenticated_requests_are_rejected_before_resolution(api_client):
    response = api_client.get("/ctx")
    assert response.status_code == 401


def test_get_queryset_is_scoped_to_the_household(owner, member, outsider, owner_client):
    response = owner_client.get("/members")
    ids = {row["id"] for row in response.json()}
    assert ids == {str(owner.pk), str(member.pk)}
