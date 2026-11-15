"""Categories: system ones read-only, household ones editable (requirements §8.9, §12.8)."""

import pytest
from django.urls import reverse

from apps.products.models import ProductCategory
from tests.factories import CategoryFactory, ProductFactory
from tests.utils import error_code

pytestmark = pytest.mark.django_db
CATEGORIES = reverse("api-v1:categories-list")


def detail(category) -> str:
    return reverse("api-v1:categories-detail", kwargs={"pk": category.pk})


def test_list_system_and_own_categories(owner, owner_client):
    own = CategoryFactory(household=owner.household, name="Κάβα", slug="kava")
    CategoryFactory()  # another household's
    ProductFactory(household=owner.household, category=own)
    rows = owner_client.get(CATEGORIES).json()
    assert len(rows) == 20  # 19 system + 1 own
    names = [row["name"] for row in rows]
    assert names == sorted(names)
    kava = next(row for row in rows if row["name"] == "Κάβα")
    assert (kava["is_system"], kava["product_count"]) == (False, 1)
    assert next(row for row in rows if row["slug"] == "groceries")["is_system"] is True


def test_create_rename_and_delete(owner, owner_client):
    response = owner_client.post(CATEGORIES, {"name": "  Κάβα & ποτά "}, format="json")
    assert response.status_code == 201
    created = response.json()
    assert (created["name"], created["slug"], created["is_system"]) == (
        "Κάβα & ποτά",
        "κάβα-ποτά",
        False,
    )
    category = ProductCategory.objects.get(pk=created["id"])
    assert category.household == owner.household

    renamed = owner_client.patch(detail(category), {"name": "Ποτά"}, format="json")
    assert (renamed.status_code, renamed.json()["slug"]) == (200, "ποτά")
    assert owner_client.delete(detail(category)).status_code == 204
    assert not ProductCategory.objects.filter(pk=category.pk).exists()


@pytest.mark.parametrize("name", ["Groceries", "groceries", "Κάβα", "   "])
def test_names_must_be_new(owner, owner_client, name):
    CategoryFactory(household=owner.household, name="Κάβα", slug="κάβα")
    response = owner_client.post(CATEGORIES, {"name": name}, format="json")
    assert (response.status_code, error_code(response)) == (400, "validation_error")


def test_other_households_may_reuse_a_name(owner, owner_client):
    CategoryFactory(name="Κάβα", slug="κάβα")
    assert owner_client.post(CATEGORIES, {"name": "Κάβα"}, format="json").status_code == 201


def test_system_categories_are_read_only(owner_client):
    groceries = ProductCategory.objects.get(household=None, slug="groceries")
    assert owner_client.get(detail(groceries)).status_code == 200
    for response in (
        owner_client.patch(detail(groceries), {"name": "Mine"}, format="json"),
        owner_client.delete(detail(groceries)),
    ):
        assert (response.status_code, error_code(response)) == (403, "system_category")
    groceries.refresh_from_db()
    assert groceries.name == "Groceries"


def test_a_category_in_use_cannot_be_deleted(owner, owner_client):
    category = CategoryFactory(household=owner.household)
    ProductFactory(household=owner.household, category=category)
    response = owner_client.delete(detail(category))
    assert (response.status_code, error_code(response)) == (409, "category_in_use")


def test_members_manage_categories_too(member_client):
    assert member_client.post(CATEGORIES, {"name": "Δώρα"}, format="json").status_code == 201
