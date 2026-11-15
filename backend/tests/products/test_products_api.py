"""Product endpoints: list, create, edit, prices, comparison, merge (requirements §12.7)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.products.models import Product, ProductCategory
from apps.receipts.models import Receipt
from tests.factories import CategoryFactory, ProductFactory
from tests.receipts.importing import elsewhere, parsed, store
from tests.utils import error_code

pytestmark = pytest.mark.django_db
PRODUCTS = reverse("api-v1:products-list")
MILK = 4  # "ΚΟΖΑΝΗΣ ΦΡΕΣΚΟ ΓΑΛΑ ΠΛΗΡΕΣ 1L": 1 piece at 1.25, package 1 l


def url(name, product) -> str:
    return reverse(f"api-v1:products-{name}", kwargs={"pk": product.pk})


@pytest.fixture
def metro(owner) -> Receipt:
    return store(owner, parsed())


def milk_product(receipt) -> Product:
    return receipt.items.get(line_number=MILK).product


# --- list, create, edit ----------------------------------------------------------------
def test_list_and_filter_products(owner, owner_client, metro):
    body = owner_client.get(PRODUCTS).json()
    assert body["count"] == 5
    names = [row["name"] for row in body["results"]]
    assert names == sorted(names)
    assert {row["line_count"] for row in body["results"]} == {1}

    found = owner_client.get(PRODUCTS, {"q": "φρέσκο γάλα"}).json()["results"]
    assert {row["name"] for row in found} == {
        "ΚΟΖΑΝΗΣ ΦΡΕΣΚΟ ΓΑΛΑ ΠΛΗΡΕΣ 1L",
        "ΚΟΖΑΝΗΣ ΦΡΕΣΚΟ ΓΑΛΑ ΕΛΑΦΡΥ 1,5% 1L",
    }
    by_merchant = owner_client.get(PRODUCTS, {"merchant": str(metro.merchant_id)}).json()
    assert by_merchant["count"] == 5
    other_store = owner_client.get(PRODUCTS, {"merchant": str(metro.store_id)}).json()
    assert other_store["count"] == 0

    product = milk_product(metro)
    category = ProductCategory.objects.get(slug="dairy-and-eggs")
    Product.objects.filter(pk=product.pk).update(category=category, brand="Κοζάνης")
    assert owner_client.get(PRODUCTS, {"category": str(category.pk)}).json()["count"] == 1
    assert owner_client.get(PRODUCTS, {"brand": "κοζάνης"}).json()["count"] == 1


def test_list_query_count(owner, owner_client, metro, django_assert_max_num_queries):
    with django_assert_max_num_queries(6):
        assert owner_client.get(PRODUCTS).json()["count"] == 5


def test_create_a_product(owner, owner_client):
    category = ProductCategory.objects.get(slug="beverages")  # a system category
    response = owner_client.post(
        PRODUCTS,
        {
            "name": "Νερό",
            "brand": "Ζαγόρι",
            "category_id": str(category.pk),
            "package_quantity": "1.5",
            "package_unit": "l",
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["category"] == {
        "id": str(category.pk),
        "name": "Beverages",
        "slug": "beverages",
        "is_system": True,
    }
    assert (body["package_quantity"], body["package_unit"], body["line_count"]) == (
        "1.5000",
        "l",
        0,
    )
    assert Product.objects.get(pk=body["id"]).household == owner.household


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"name": "x", "package_quantity": "1"}, "package_quantity"),
        ({"name": "x", "package_unit": "l"}, "package_quantity"),
        ({"name": "x", "package_quantity": "0", "package_unit": "l"}, "package_quantity"),
        ({"name": "x", "package_unit": "oz", "package_quantity": "1"}, "package_unit"),
        ({"brand": "no name"}, "name"),
    ],
)
def test_create_validation(owner_client, payload, field):
    response = owner_client.post(PRODUCTS, payload, format="json")
    assert (response.status_code, error_code(response)) == (400, "validation_error")
    assert field in response.json()["error"]["details"]


def test_categories_of_other_households_are_refused(owner, owner_client):
    own = CategoryFactory(household=owner.household)
    foreign = CategoryFactory()
    ok = owner_client.post(PRODUCTS, {"name": "x", "category_id": str(own.pk)}, format="json")
    assert ok.status_code == 201
    response = owner_client.post(
        PRODUCTS, {"name": "x", "category_id": str(foreign.pk)}, format="json"
    )
    assert response.status_code == 400
    assert "category_id" in response.json()["error"]["details"]


def test_edit_a_product_recomputes_prices(owner_client, metro):
    product = milk_product(metro)
    response = owner_client.patch(
        url("detail", product),
        {"name": "Γάλα", "package_quantity": "500", "package_unit": "ml", "category_id": None},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Γάλα"
    item = metro.items.get(line_number=MILK)
    assert item.normalized_unit_price == Decimal("2.5000")
    product.refresh_from_db()
    assert product.normalized_name == "ΓΑΛΑ"

    half = owner_client.patch(url("detail", product), {"package_unit": None}, format="json")
    assert half.status_code == 400  # quantity without a unit


# --- price history -----------------------------------------------------------------------
def test_price_history(owner, owner_client, metro):
    product = milk_product(metro)
    later = elsewhere(parsed(), vat=metro.merchant.vat_number, key="3", prices={MILK: "1.35"})
    later = store(owner, later)
    Receipt.objects.filter(pk=later.pk).update(issued_at=metro.issued_at + timedelta(days=7))

    body = owner_client.get(url("prices", product)).json()
    assert body["count"] == 2
    newest, oldest = body["results"]
    assert (newest["receipt_id"], newest["gross_amount"]) == (str(later.pk), "1.35")
    assert newest["merchant"]["display_name"] == "Metro"
    assert oldest["store"]["name"] == metro.store.label
    assert (oldest["normalized_unit"], oldest["normalized_unit_price"]) == ("l", "1.2500")
    assert body["stats"] == [
        {
            "normalized_unit": "l",
            "currency": "EUR",
            "count": 2,
            "latest": "1.3500",
            "previous": "1.2500",
            "minimum": "1.2500",
            "maximum": "1.3500",
            "average": "1.3000",
        }
    ]

    # Statistics cover every matching entry, not just the page.
    page = owner_client.get(url("prices", product), {"page_size": 1}).json()
    assert (len(page["results"]), page["stats"][0]["count"]) == (1, 2)

    day = metro.issued_at.date()
    to_first_day = owner_client.get(url("prices", product), {"issued_to": day.isoformat()})
    assert to_first_day.json()["count"] == 1
    from_later = owner_client.get(
        url("prices", product), {"issued_from": (day + timedelta(days=1)).isoformat()}
    )
    assert [row["receipt_id"] for row in from_later.json()["results"]] == [str(later.pk)]
    assert owner_client.get(url("prices", product), {"normalized_unit": "kg"}).json()["count"] == 0
    assert owner_client.get(url("prices", product), {"merchant": "nope"}).status_code == 400


def test_cancelled_receipts_leave_price_history(owner_client, metro):
    Receipt.objects.filter(pk=metro.pk).update(status=Receipt.Status.CANCELLED)
    body = owner_client.get(url("prices", milk_product(metro))).json()
    assert (body["count"], body["stats"]) == (0, [])


# --- comparison and merge (the M4 exit scenario) -----------------------------------------
def test_cross_merchant_comparison_after_merging(owner, owner_client, metro):
    """The same receipt from two merchants, then the two milk products merged."""
    other = store(owner, elsewhere(parsed(), name="ΦΘΗΝΟ ΜΑΓΑΖΙ ΑΕ", prices={MILK: "1.15"}))
    target, source = milk_product(metro), milk_product(other)

    one = owner_client.get(url("price-comparison", target)).json()
    assert (one["comparable"], one["reason"]) == (False, "one_merchant")
    assert one["merchants"][0]["rank"] is None

    response = owner_client.post(
        url("merge", target), {"source_product_ids": [str(source.pk)]}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["line_count"] == 2
    assert not Product.objects.filter(pk=source.pk).exists()

    body = owner_client.get(url("price-comparison", target)).json()
    assert (body["comparable"], body["reason"]) == (True, None)
    assert (body["normalized_unit"], body["currency"]) == ("l", "EUR")
    ranking = [
        (row["rank"], row["merchant"]["display_name"], row["stats"]["average"])
        for row in body["merchants"]
    ]
    assert ranking == [(1, "Φθηνο Μαγαζι", "1.1500"), (2, "Metro", "1.2500")]
    assert body["available_units"] == [{"normalized_unit": "l", "currency": "EUR", "count": 2}]


def test_comparison_never_ranks_incompatible_units(owner, owner_client, metro):
    juice = metro.items.get(line_number=3).product  # 27/250ML: no package size → per piece
    other = store(owner, elsewhere(parsed()))
    owner_client.post(
        url("merge", juice),
        {"source_product_ids": [str(other.items.get(line_number=3).product_id)]},
        format="json",
    )
    by_piece = owner_client.get(url("price-comparison", juice)).json()
    assert (by_piece["comparable"], by_piece["normalized_unit"]) == (True, "piece")

    no_prices = owner_client.get(url("price-comparison", juice), {"normalized_unit": "kg"})
    assert no_prices.json()["comparable"] is False
    assert no_prices.json()["reason"] == "no_prices"

    item = metro.items.get(line_number=3)
    item.unit = "other"
    item.save()
    from apps.products.prices import refresh_product_prices

    refresh_product_prices(juice)
    unknown = owner_client.get(url("price-comparison", juice), {"normalized_unit": "other"})
    assert (unknown.json()["comparable"], unknown.json()["reason"]) == (False, "unknown_unit")


def test_comparison_period(owner, owner_client, metro):
    product = milk_product(metro)
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    body = owner_client.get(url("price-comparison", product), {"issued_from": tomorrow}).json()
    assert body["reason"] == "no_prices"


@pytest.mark.parametrize("case", ["self", "foreign", "empty"])
def test_merge_validation(owner_client, metro, case):
    target = milk_product(metro)
    ids = {"self": [str(target.pk)], "foreign": [str(ProductFactory().pk)], "empty": []}[case]
    response = owner_client.post(url("merge", target), {"source_product_ids": ids}, format="json")
    assert (response.status_code, error_code(response)) == (400, "validation_error")
    assert Product.objects.filter(pk=target.pk).exists()


def test_authentication_is_required(api_client):
    assert api_client.get(PRODUCTS).status_code == 401


def test_system_categories_are_seeded():
    system = ProductCategory.objects.filter(household__isnull=True)
    assert system.count() == 19
    assert system.filter(slug="restaurants-and-cafes", name="Restaurants and cafés").exists()
