import io

import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import User
from apps.households.models import Household, HouseholdMember

pytestmark = pytest.mark.django_db
PASSWORD = "Bootstrap-Pass-2026"


def run(*args, **kwargs) -> str:
    out = io.StringIO()
    call_command("bootstrap_household", *args, stdout=out, **kwargs)
    return out.getvalue()


@pytest.fixture
def password_env(monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_PASSWORD", PASSWORD)
    return "BOOTSTRAP_PASSWORD"


def test_creates_owner_and_household(password_env):
    output = run(
        "--email", "Owner@Example.com", "--household", "Home", "--password-env", password_env
    )
    user = User.objects.get(email="owner@example.com")
    assert user.check_password(PASSWORD)
    membership = HouseholdMember.objects.get(user=user)
    assert membership.household.name == "Home"
    assert membership.role == HouseholdMember.Role.OWNER
    assert 'Created household "Home"' in output


def test_is_idempotent(password_env):
    run("--email", "owner@example.com", "--household", "Home", "--password-env", password_env)
    output = run("--email", "owner@example.com", "--household", "Home")
    assert "already exists" in output
    assert Household.objects.count() == 1


def test_existing_user_gets_another_household_and_admin_access(password_env):
    run("--email", "owner@example.com", "--household", "Home", "--password-env", password_env)
    output = run("--email", "owner@example.com", "--household", "Cottage", "--superuser")
    user = User.objects.get(email="owner@example.com")
    assert user.is_staff
    assert user.is_superuser
    assert "Granted admin access" in output
    assert set(Household.objects.values_list("name", flat=True)) == {"Home", "Cottage"}


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--email", " ", "--household", "Home"], "must not be empty"),
        (["--email", "a@example.com", "--household", "Home", "--password-env", "NOPE"], "NOPE"),
        (["--email", "a@example.com", "--household", "Home"], "No TTY"),
    ],
)
def test_input_errors(args, message):
    with pytest.raises(CommandError, match=message):
        run(*args)


def test_weak_password_is_rejected(monkeypatch):
    monkeypatch.setenv("WEAK", "123")
    with pytest.raises(CommandError):
        run("--email", "a@example.com", "--household", "Home", "--password-env", "WEAK")


def test_interactive_password_prompt(monkeypatch):
    answers = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(answers))
    run("--email", "tty@example.com", "--household", "Home")
    assert User.objects.get(email="tty@example.com").check_password(PASSWORD)


def test_interactive_password_mismatch(monkeypatch):
    answers = iter([PASSWORD, "different"])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(answers))
    with pytest.raises(CommandError, match="do not match"):
        run("--email", "tty@example.com", "--household", "Home")
