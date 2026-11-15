"""Receipt list filters and search (requirements §12.5)."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse

from apps.products.models import ProductCategory
from apps.receipts.models import Receipt, ReceiptItem
from tests.factories import (
    MerchantFactory,
    ProductFactory,
    ReceiptFactory,
    ReceiptItemFactory,
    StoreFactory,
)

pytestmark = pytest.mark.django_db
RECEIPTS = reverse("api-v1:receipts-list")
ATHENS = ZoneInfo("Europe/Athens")


@pytest.fixture
def shops(owner):
    """Three receipts: METRO (dairy product, warning), LIDL (needs review), fuel (credit)."""
    dairy = ProductCategory.objects.get(household=None, slug="dairy-and-eggs")
    fuel = ProductCategory.objects.get(household=None, slug="fuel-and-transport")
    metro = MerchantFactory(display_name="Metro", legal_name="METRO ΑΕΒΕ")
    lidl = MerchantFactory(display_name="Lidl", legal_name="LIDL ΕΛΛΑΣ")
    station = MerchantFactory(display_name="Πρατήριο", default_category=fuel)
    store = StoreFactory(merchant=metro)
    milk = ProductFactory(household=owner.household, name="Γάλα", category=dairy)

    first = ReceiptFactory(
        household=owner.household,
        merchant=metro,
        store=store,
        gross_total=Decimal("9.15"),
        issued_at=datetime(2026, 11, 1, 0, 30, tzinfo=ATHENS),  # 22:30 UTC on Oct 31
        validation_warnings=[{"code": "totals_mismatch"}],
    )
    ReceiptItemFactory(
        receipt=first, description="ΚΟΖΑΝΗΣ ΦΡΕΣΚΟ ΓΑΛΑ 1L", product=milk, match_status="matched"
    )
    second = ReceiptFactory(
        household=owner.household,
        merchant=lidl,
        gross_total=Decimal("75.48"),
        issued_at=datetime(2026, 11, 10, 12, tzinfo=ATHENS),
    )
    ReceiptItemFactory(receipt=second, description="ΚΑΡΠΟΥΖΙ")  # needs review
    third = ReceiptFactory(
        household=owner.household,
        merchant=station,
        gross_total=Decimal("50.00"),
        issued_at=datetime(2026, 11, 20, 8, tzinfo=ATHENS),
        document_kind=Receipt.Kind.CREDIT_NOTE,
        status=Receipt.Status.CANCELLED,
    )
    return {
        "metro": first,
        "lidl": second,
        "fuel": third,
        "milk": milk,
        "dairy": dairy,
        "fuel_category": fuel,
    }


def ids(client, **params) -> set[str]:
    response = client.get(RECEIPTS, params)
    assert response.status_code == 200, response.json()
    return {row["id"] for row in response.json()["results"]}


def pk(*receipts) -> set[str]:
    return {str(receipt.pk) for receipt in receipts}


def test_filters(owner_client, shops):
    metro, lidl, fuel = shops["metro"], shops["lidl"], shops["fuel"]
    assert ids(owner_client) == pk(metro, lidl, fuel)
    assert ids(owner_client, issued_from="2026-11-01") == pk(metro, lidl, fuel)  # household day
    assert ids(owner_client, issued_to="2026-10-31") == set()
    assert ids(owner_client, issued_from="2026-11-05", issued_to="2026-11-10") == pk(lidl)
    assert ids(owner_client, merchant=metro.merchant_id) == pk(metro)
    assert ids(owner_client, store=metro.store_id) == pk(metro)
    assert ids(owner_client, min_total="50", max_total="75.48") == pk(lidl, fuel)
    assert ids(owner_client, product=shops["milk"].pk) == pk(metro)
    assert ids(owner_client, category=shops["dairy"].pk) == pk(metro)
    assert ids(owner_client, category=shops["fuel_category"].pk) == pk(fuel)  # merchant default
    assert ids(owner_client, needs_review="true") == pk(lidl)
    assert ids(owner_client, needs_review="false") == pk(metro, fuel)
    assert ids(owner_client, has_warnings="true") == pk(metro)
    assert ids(owner_client, has_warnings="false") == pk(lidl, fuel)
    assert ids(owner_client, status="cancelled") == pk(fuel)
    assert ids(owner_client, document_kind="credit_note") == pk(fuel)


def test_search(owner_client, shops):
    assert ids(owner_client, q="φρέσκο γάλα") == pk(shops["metro"])  # line text, accents ignored
    assert ids(owner_client, q="lidl") == pk(shops["lidl"])  # merchant name
    assert ids(owner_client, q="πρατήριο") == pk(shops["fuel"])
    assert ids(owner_client, q="  ") == pk(shops["metro"], shops["lidl"], shops["fuel"])


def test_line_filters_do_not_duplicate_receipts(owner, owner_client, shops):
    for number in range(2, 5):
        ReceiptItemFactory(
            receipt=shops["metro"],
            line_number=number,
            description="ΓΑΛΑ",
            product=shops["milk"],
            match_status="matched",
        )
    body = owner_client.get(RECEIPTS, {"q": "γαλα", "product": shops["milk"].pk}).json()
    assert body["count"] == 1
    assert body["results"][0]["item_count"] == 4


@pytest.mark.parametrize(
    "params",
    [{"issued_from": "soon"}, {"merchant": "nope"}, {"status": "lost"}, {"min_total": "x"}],
)
def test_invalid_filters(owner_client, params):
    assert owner_client.get(RECEIPTS, params).status_code == 400


def test_filtered_list_query_count(owner_client, shops, django_assert_max_num_queries):
    with django_assert_max_num_queries(6):
        owner_client.get(
            RECEIPTS, {"q": "γαλα", "needs_review": "false", "category": shops["dairy"].pk}
        )


def test_ordering(owner_client, shops):
    rows = owner_client.get(RECEIPTS, {"ordering": "-gross_total"}).json()["results"]
    assert [row["gross_total"] for row in rows] == ["75.48", "50.00", "9.15"]
    rows = owner_client.get(RECEIPTS, {"ordering": "issued_at"}).json()["results"]
    assert rows[0]["id"] == str(shops["metro"].pk)
    assert ReceiptItem.objects.count() == 2
