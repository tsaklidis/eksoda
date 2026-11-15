from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.products.models import MerchantProductMapping, Product, ProductCategory
from apps.receipts.models import ReceiptItem
from tests.receipts.importing import parsed, store

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    admin = User.objects.create_superuser(email="admin@example.com", password="x-Secret-123")
    client.force_login(admin)
    return client


@pytest.fixture
def receipt(owner):
    return store(owner, parsed())


def test_admin_pages_load(admin_client, receipt):
    product = Product.objects.first()
    mapping = MerchantProductMapping.objects.first()
    category = ProductCategory.objects.first()
    urls = [
        reverse("admin:products_product_changelist") + "?q=ΓΑΛΑ",
        reverse("admin:products_product_change", args=[product.pk]),
        reverse("admin:products_merchantproductmapping_changelist"),
        reverse("admin:products_merchantproductmapping_change", args=[mapping.pk]),
        reverse("admin:products_productcategory_changelist") + "?household__isempty=1",
        reverse("admin:products_productcategory_change", args=[category.pk]),
        reverse("admin:merchants_merchant_change", args=[receipt.merchant_id]),
        reverse("admin:receipts_receiptitem_changelist") + "?normalized_unit=kg",
    ]
    for url in urls:
        assert admin_client.get(url).status_code == 200, url


def test_package_change_in_the_admin_recomputes_prices(admin_client, receipt):
    item = receipt.items.get(line_number=4)
    product = item.product
    response = admin_client.post(
        reverse("admin:products_product_change", args=[product.pk]),
        {
            "name": product.name,
            "brand": "",
            "category": "",
            "package_quantity": "500",
            "package_unit": "ml",
            "mappings-TOTAL_FORMS": "1",
            "mappings-INITIAL_FORMS": "1",
            "mappings-MIN_NUM_FORMS": "0",
            "mappings-MAX_NUM_FORMS": "1000",
            "mappings-0-id": str(product.mappings.get().pk),
            "mappings-0-product": str(product.pk),
        },
    )
    assert response.status_code == 302, response.content.decode()[:2000]
    item.refresh_from_db()
    assert item.normalized_unit_price == Decimal("2.5000")


def test_receipt_actions_rematch_and_recompute(admin_client, receipt):
    receipt.items.update(
        product=None,
        match_status=ReceiptItem.MatchStatus.NEEDS_REVIEW,
        normalized_unit_price=None,
        normalized_quantity=None,
        normalized_unit=None,
    )
    changelist = reverse("admin:receipts_receipt_changelist")
    response = admin_client.post(
        changelist, {"action": "rematch", "_selected_action": [receipt.pk]}, follow=True
    )
    assert "Matched 5 line(s)." in [str(m) for m in response.context["messages"]]
    assert not receipt.items.filter(product__isnull=True).exists()

    receipt.items.update(normalized_unit_price=None)
    admin_client.post(changelist, {"action": "recompute_prices", "_selected_action": [receipt.pk]})
    assert not receipt.items.filter(normalized_unit_price__isnull=True).exists()


def test_product_recompute_action(admin_client, receipt):
    receipt.items.update(normalized_unit_price=None)
    response = admin_client.post(
        reverse("admin:products_product_changelist"),
        {
            "action": "recompute_prices",
            "_selected_action": list(Product.objects.values_list("pk", flat=True)),
        },
        follow=True,
    )
    assert "Recomputed 5 product(s)." in [str(m) for m in response.context["messages"]]
    assert not receipt.items.filter(normalized_unit_price__isnull=True).exists()


def test_products_and_mappings_are_not_added_by_hand(admin_client):
    for model in ("product", "merchantproductmapping"):
        assert admin_client.get(reverse(f"admin:products_{model}_add")).status_code == 403
