"""Review endpoints on receipt lines (requirements §12.6)."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.products.models import MerchantProductMapping, Product
from apps.receipts.models import ReceiptItem
from tests.factories import ProductFactory
from tests.receipts.importing import parsed, store
from tests.utils import error_code

pytestmark = pytest.mark.django_db
REVIEW = reverse("api-v1:receipt-items-review")
MILK = 4


def url(name, item) -> str:
    return reverse(f"api-v1:receipt-items-{name}", kwargs={"pk": item.pk})


@pytest.fixture
def receipt(owner):
    return store(owner, parsed())


@pytest.fixture
def milk(receipt) -> ReceiptItem:
    return receipt.items.get(line_number=MILK)


def test_review_lists_lines_waiting_for_a_person(owner_client, receipt, milk):
    assert owner_client.get(REVIEW).json()["count"] == 0
    ReceiptItem.objects.filter(pk=milk.pk).update(product=None, match_status="needs_review")
    body = owner_client.get(REVIEW).json()
    assert body["count"] == 1
    row = body["results"][0]
    assert row["id"] == str(milk.pk)
    assert row["receipt"]["merchant_name"] == "Metro"
    assert row["receipt"]["currency"] == "EUR"
    assert (row["product"], row["match_status"]) == (None, "needs_review")


def test_match_a_line(owner, owner_client, milk):
    chosen = ProductFactory(household=owner.household, name="Γάλα")
    response = owner_client.post(url("match", milk), {"product_id": str(chosen.pk)}, format="json")
    assert response.status_code == 200
    body = response.json()
    assert body["product"] == {"id": str(chosen.pk), "name": "Γάλα"}
    assert (body["match_status"], body["normalized_unit"]) == ("matched", "piece")
    assert MerchantProductMapping.objects.get(merchant_product_code="652432").product == chosen


def test_match_refuses_other_households_products(owner_client, milk):
    foreign = ProductFactory()
    response = owner_client.post(url("match", milk), {"product_id": str(foreign.pk)}, format="json")
    assert (response.status_code, error_code(response)) == (400, "validation_error")
    milk.refresh_from_db()
    assert milk.product != foreign


def test_non_product_lines_cannot_be_matched(owner, owner_client, milk):
    owner_client.patch(url("detail", milk), {"line_type": "fee"}, format="json")
    chosen = ProductFactory(household=owner.household)
    response = owner_client.post(url("match", milk), {"product_id": str(chosen.pk)}, format="json")
    assert (response.status_code, error_code(response)) == (409, "not_a_product_line")


def test_create_a_product_from_a_line(owner_client, milk):
    response = owner_client.post(
        url("create-product", milk),
        {"name": "Γάλα πλήρες", "package_quantity": "1", "package_unit": "l"},
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["product"]["name"] == "Γάλα πλήρες"
    assert body["normalized_unit_price"] == "1.2500"
    assert Product.objects.filter(name="Γάλα πλήρες").count() == 1

    invalid = owner_client.post(url("create-product", milk), {"brand": "x"}, format="json")
    assert invalid.status_code == 400


def test_reclassify_a_line(owner_client, milk):
    response = owner_client.patch(
        url("detail", milk), {"line_type": "discount", "user_note": "coupon"}, format="json"
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["line_type"], body["match_status"], body["product"]) == (
        "discount",
        "not_a_product",
        None,
    )
    assert body["user_note"] == "coupon"
    back = owner_client.patch(url("detail", milk), {"line_type": "product"}, format="json")
    assert (back.json()["match_status"], back.json()["normalized_unit_price"]) == (
        "matched",
        "1.2500",
    )
    milk.refresh_from_db()
    assert milk.gross_amount == Decimal("1.25")  # source values never change
    assert (
        owner_client.patch(url("detail", milk), {"line_type": "x"}, format="json").status_code
        == 400
    )


def test_line_notes_are_limited(owner_client, milk):
    response = owner_client.patch(url("detail", milk), {"user_note": "x" * 2001}, format="json")
    assert response.status_code == 400
