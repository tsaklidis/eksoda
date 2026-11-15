import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_create_user_lowercases_and_hashes():
    user = User.objects.create_user(email="Mixed.Case@Example.COM", password="x-Secret-123")
    assert user.email == "mixed.case@example.com"
    assert user.check_password("x-Secret-123")
    assert not user.is_staff
    assert str(user) == "mixed.case@example.com"


def test_create_user_requires_email():
    with pytest.raises(ValueError, match="email"):
        User.objects.create_user(email="", password="x")


def test_create_superuser_sets_flags():
    admin = User.objects.create_superuser(email="admin@example.com", password="x-Secret-123")
    assert admin.is_staff
    assert admin.is_superuser


def test_create_superuser_rejects_non_staff():
    with pytest.raises(ValueError, match="is_staff"):
        User.objects.create_superuser(email="a@example.com", password="x", is_staff=False)


def test_natural_key_lookup_is_case_insensitive():
    user = User.objects.create_user(email="someone@example.com", password="x")
    assert User.objects.get_by_natural_key("SomeOne@Example.com") == user


def test_email_uniqueness_is_case_insensitive_in_the_database():
    User.objects.create_user(email="dup@example.com", password="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        User(email="DUP@example.com").save()  # bypasses the manager's lowercasing


def test_clean_normalizes_email():
    user = User(email="Clean@Example.COM")
    user.clean()
    assert user.email == "clean@example.com"
