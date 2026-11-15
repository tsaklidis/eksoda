import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.households.services import create_invitation

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    admin = User.objects.create_superuser(email="admin@example.com", password="x-Secret-123")
    client.force_login(admin)
    return client


def test_admin_pages_load(admin_client, owner):
    create_invitation(household=owner.household, created_by=owner.user)
    urls = [
        reverse("admin:accounts_user_changelist"),
        reverse("admin:accounts_user_add"),
        reverse("admin:accounts_user_change", args=[owner.user.pk]),
        reverse("admin:households_household_changelist"),
        reverse("admin:households_household_change", args=[owner.household.pk]),
        reverse("admin:households_householdinvitation_changelist"),
    ]
    for url in urls:
        assert admin_client.get(url).status_code == 200, url


def test_invitations_cannot_be_added_in_admin(admin_client):
    assert admin_client.get(reverse("admin:households_householdinvitation_add")).status_code == 403


def test_admin_add_user_form(admin_client):
    url = reverse("admin:accounts_user_add")
    data = {
        "email": "Added@Example.com",
        "display_name": "Added",
        "password1": "Str0ng-Admin-Pass",
        "password2": "Str0ng-Admin-Pass",
    }
    response = admin_client.post(url, data)
    assert response.status_code == 302
    user = User.objects.get(email="added@example.com")
    assert user.check_password("Str0ng-Admin-Pass")


def test_admin_add_user_form_errors(admin_client):
    url = reverse("admin:accounts_user_add")
    User.objects.create_user(email="taken@example.com", password="x")
    response = admin_client.post(
        url, {"email": "TAKEN@example.com", "password1": "Str0ng-A1", "password2": "different"}
    )
    form = response.context["adminform"].form
    assert "email" in form.errors
    assert "password2" in form.errors


def test_admin_change_user_form(admin_client, owner):
    url = reverse("admin:accounts_user_change", args=[owner.user.pk])
    data = {"email": "Changed@Example.com", "display_name": "Changed", "is_active": "on"}
    assert admin_client.post(url, data).status_code == 302
    owner.user.refresh_from_db()
    assert (owner.user.email, owner.user.display_name) == ("changed@example.com", "Changed")


def test_admin_login_is_rate_limited(client, monkeypatch):
    from apps.accounts.throttles import AdminLoginRateThrottle

    monkeypatch.setattr(AdminLoginRateThrottle, "THROTTLE_RATES", {"admin_login": "2/min"})
    login = reverse("admin:login")
    credentials = {"username": "admin@example.com", "password": "wrong"}
    for _ in range(2):
        assert client.post(login, credentials).status_code == 200  # the form, with an error
    assert client.post(login, credentials).status_code == 429
    assert client.get(login).status_code == 200  # the page itself is never throttled
