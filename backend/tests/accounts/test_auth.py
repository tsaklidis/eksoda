import pytest
from django.urls import reverse

from tests.factories import DEFAULT_PASSWORD, UserFactory
from tests.utils import client_for, error_code

pytestmark = pytest.mark.django_db

LOGIN = reverse("api-v1:auth-login")
REFRESH = reverse("api-v1:auth-refresh")
LOGOUT = reverse("api-v1:auth-logout")
ME = reverse("api-v1:auth-me")
PASSWORD = reverse("api-v1:auth-password-change")


def login(client, email, password=DEFAULT_PASSWORD):
    return client.post(LOGIN, {"email": email, "password": password}, format="json")


def test_login_is_case_insensitive_and_returns_tokens(api_client, owner):
    response = login(api_client, owner.user.email.upper())
    assert response.status_code == 200
    assert set(response.json()) == {"access", "refresh"}
    owner.user.refresh_from_db()
    assert owner.user.last_login is not None


def test_login_with_wrong_password(api_client, owner):
    response = login(api_client, owner.user.email, "wrong-password")
    assert response.status_code == 401
    assert error_code(response) == "no_active_account"


def test_login_is_rate_limited_per_ip_and_email(api_client, owner):
    for _ in range(5):
        assert login(api_client, owner.user.email, "wrong").status_code == 401
    response = login(api_client, owner.user.email, "wrong")
    assert response.status_code == 429
    assert error_code(response) == "rate_limited"
    assert response.json()["error"]["details"]["retry_after_seconds"] > 0
    # Another email from the same IP is still allowed (until the per-IP limit).
    assert login(api_client, "someone@example.com", "wrong").status_code == 401


def test_refresh_rotates_and_revokes_the_old_token(api_client, owner):
    tokens = login(api_client, owner.user.email).json()
    rotated = api_client.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")
    assert rotated.status_code == 200
    assert rotated.json()["refresh"] != tokens["refresh"]

    reused = api_client.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")
    assert reused.status_code == 401
    assert error_code(reused) == "token_not_valid"


def test_logout_blacklists_the_refresh_token(api_client, owner):
    tokens = login(api_client, owner.user.email).json()
    client = client_for(owner.user)
    assert client.post(LOGOUT, {"refresh": tokens["refresh"]}, format="json").status_code == 204
    response = api_client.post(REFRESH, {"refresh": tokens["refresh"]}, format="json")
    assert response.status_code == 401


def test_logout_rejects_invalid_and_foreign_tokens(api_client, owner, outsider):
    client = client_for(owner.user)
    response = client.post(LOGOUT, {"refresh": "garbage"}, format="json")
    assert response.status_code == 400
    assert error_code(response) == "invalid_token"

    foreign = login(api_client, outsider.user.email).json()["refresh"]
    response = client.post(LOGOUT, {"refresh": foreign}, format="json")
    assert response.status_code == 400
    assert error_code(response) == "invalid_token"


def test_logout_requires_authentication(api_client):
    assert api_client.post(LOGOUT, {"refresh": "x"}, format="json").status_code == 401


def test_me_returns_profile_and_memberships(owner, owner_client):
    response = owner_client.get(ME)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == owner.user.email
    assert body["memberships"] == [
        {
            "household_id": str(owner.household_id),
            "household_name": owner.household.name,
            "role": "owner",
            "joined_at": body["memberships"][0]["joined_at"],
        }
    ]


def test_password_change_revokes_refresh_tokens(api_client, owner):
    tokens = login(api_client, owner.user.email).json()
    client = client_for(owner.user)
    new_password = "An0ther-Strong-Passphrase"

    response = client.post(
        PASSWORD,
        {"old_password": DEFAULT_PASSWORD, "new_password": new_password},
        format="json",
    )
    assert response.status_code == 204
    assert (
        api_client.post(REFRESH, {"refresh": tokens["refresh"]}, format="json").status_code == 401
    )
    assert login(api_client, owner.user.email, new_password).status_code == 200


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("wrong", "An0ther-Strong-Passphrase", "old_password"),
        (DEFAULT_PASSWORD, "123", "new_password"),
    ],
)
def test_password_change_validation(owner, old, new, field):
    response = client_for(owner.user).post(
        PASSWORD, {"old_password": old, "new_password": new}, format="json"
    )
    assert response.status_code == 400
    assert field in response.json()["error"]["details"]


def test_inactive_users_cannot_log_in(api_client):
    user = UserFactory(is_active=False)
    assert login(api_client, user.email).status_code == 401


@pytest.mark.parametrize("body", [[], "x", [{"email": "a@example.com"}]])
def test_login_with_a_non_object_body_is_a_400(api_client, body):
    response = api_client.post(LOGIN, body, format="json")
    assert response.status_code == 400
    assert error_code(response) == "validation_error"


def test_api_bodies_over_16_kb_are_rejected(api_client):
    body = '{"email": "a@example.com", "password": "' + "x" * 17000 + '"}'
    response = api_client.generic("POST", LOGIN, body, content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
