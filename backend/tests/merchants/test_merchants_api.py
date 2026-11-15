"""Merchants and stores the household bought from (requirements §12.8)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse

from apps.products.models import ProductCategory
from tests.factories import MerchantFactory, ReceiptFactory, StoreFactory

pytestmark = pytest.mark.django_db
MERCHANTS = reverse("api-v1:merchants-list")
STORES = reverse("api-v1:stores-list")
ATHENS = ZoneInfo("Europe/Athens")


@pytest.fixture
def bought(owner, outsider):
    groceries = ProductCategory.objects.get(household=None, slug="groceries")
    metro = MerchantFactory(display_name="Metro", default_category=groceries)
    lidl = MerchantFactory(display_name="Lidl")
    elsewhere = MerchantFactory(display_name="Only the other household")
    kozani, athens = StoreFactory(merchant=metro, city="ΚΟΖΑΝΗ"), StoreFactory(merchant=metro)
    for day in (1, 9):
        ReceiptFactory(
            household=owner.household,
            merchant=metro,
            store=kozani,
            issued_at=datetime(2026, 11, day, 10, tzinfo=ATHENS),
        )
    ReceiptFactory(household=owner.household, merchant=lidl)
    ReceiptFactory(household=outsider.household, merchant=elsewhere)
    ReceiptFactory(household=outsider.household, merchant=metro, store=athens)
    return {
        "metro": metro,
        "lidl": lidl,
        "elsewhere": elsewhere,
        "kozani": kozani,
        "athens": athens,
    }


def test_merchants_are_the_households_own(owner_client, bought):
    body = owner_client.get(MERCHANTS).json()
    assert [row["display_name"] for row in body["results"]] == ["Lidl", "Metro"]
    metro = body["results"][1]
    assert metro["receipt_count"] == 2  # the other household's receipt does not count
    assert metro["last_receipt_at"] == "2026-11-09T10:00:00+02:00"
    assert metro["default_category"]["slug"] == "groceries"
    detail = owner_client.get(reverse("api-v1:merchants-detail", kwargs={"pk": bought["metro"].pk}))
    assert detail.json()["receipt_count"] == 2
    other = reverse("api-v1:merchants-detail", kwargs={"pk": bought["elsewhere"].pk})
    assert owner_client.get(other).status_code == 404

    ordered = owner_client.get(MERCHANTS, {"ordering": "-receipt_count"}).json()["results"]
    assert ordered[0]["display_name"] == "Metro"


def test_stores_are_the_households_own(owner_client, bought):
    body = owner_client.get(STORES).json()
    assert [row["id"] for row in body["results"]] == [str(bought["kozani"].pk)]  # not Athens
    row = body["results"][0]
    assert row["merchant"] == {"id": str(bought["metro"].pk), "display_name": "Metro"}
    assert (row["receipt_count"], row["city"]) == (2, "ΚΟΖΑΝΗ")
    assert owner_client.get(STORES, {"merchant": bought["lidl"].pk}).json()["count"] == 0


def test_query_counts(owner_client, bought, django_assert_max_num_queries):
    for url in (MERCHANTS, STORES):
        with django_assert_max_num_queries(5):
            owner_client.get(url)


def test_authentication_is_required(api_client):
    assert api_client.get(MERCHANTS).status_code == 401
