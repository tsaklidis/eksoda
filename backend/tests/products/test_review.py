"""Corrections: link, create from a line, reclassify, edit, merge (requirements §9.3)."""

from decimal import Decimal

import pytest

from apps.households.models import Household
from apps.products.errors import LineNotProduct
from apps.products.models import MerchantProductMapping, Product
from apps.products.review import (
    create_product_for_item,
    link_item,
    merge_products,
    update_item,
    update_product,
)
from apps.receipts.models import ReceiptItem
from tests.factories import MemberFactory, ProductFactory
from tests.receipts.importing import elsewhere, parsed, store

pytestmark = pytest.mark.django_db
MatchStatus = ReceiptItem.MatchStatus
MILK = 4  # "ΚΟΖΑΝΗΣ ΦΡΕΣΚΟ ΓΑΛΑ ΠΛΗΡΕΣ 1L", code 652432, 1 piece, 1.25


@pytest.fixture
def member():
    return MemberFactory()


@pytest.fixture
def receipt(member):
    return store(member, parsed())


def milk(receipt) -> ReceiptItem:
    return receipt.items.select_related("product", "receipt").get(line_number=MILK)


def test_link_remembers_the_item_and_deletes_the_orphan(member, receipt):
    item = milk(receipt)
    auto = item.product
    chosen = ProductFactory(
        household=member.household, package_quantity=Decimal("500"), package_unit="ml"
    )

    link_item(item, chosen)
    item.refresh_from_db()
    assert (item.product, item.match_status) == (chosen, MatchStatus.MATCHED)
    assert (item.normalized_unit, item.normalized_unit_price) == ("l", Decimal("2.5000"))
    mapping = MerchantProductMapping.objects.get(merchant_product_code="652432")
    assert mapping.product == chosen
    assert not Product.objects.filter(pk=auto.pk).exists()  # no lines, no mappings left

    # The next import of that item from the same merchant matches the chosen product.
    vat = receipt.merchant.vat_number
    again = store(member, elsewhere(parsed(), vat=vat, key="3"))
    assert again.items.get(line_number=MILK).product == chosen


def test_link_keeps_a_product_that_still_has_lines(member, receipt):
    item = milk(receipt)
    auto = item.product
    other = store(member, elsewhere(parsed(), vat=receipt.merchant.vat_number, key="3"))
    assert milk(other).product == auto
    link_item(item, ProductFactory(household=member.household))
    assert Product.objects.filter(pk=auto.pk).exists()


def test_only_product_lines_can_be_linked(member, receipt):
    item = milk(receipt)
    update_item(item, line_type=ReceiptItem.LineType.OTHER)
    with pytest.raises(LineNotProduct):
        link_item(item, ProductFactory(household=member.household))
    with pytest.raises(LineNotProduct):
        create_product_for_item(item, name="x")


def test_create_a_product_from_a_line(receipt):
    item = milk(receipt)
    create_product_for_item(
        item, name="Γάλα πλήρες", brand="Κοζάνης", package_quantity=Decimal(1), package_unit="l"
    )
    item.refresh_from_db()
    assert (item.product.name, item.product.brand) == ("Γάλα πλήρες", "Κοζάνης")
    assert item.product.normalized_name == "ΓΑΛΑ ΠΛΗΡΕΣ"
    assert MerchantProductMapping.objects.get(merchant_product_code="652432").product == (
        item.product
    )


def test_reclassify_and_back(receipt):
    item = milk(receipt)
    auto = item.product
    update_item(item, line_type=ReceiptItem.LineType.FEE, user_note="deposit")
    item.refresh_from_db()
    assert (item.line_type, item.match_status, item.product) == ("fee", "not_a_product", None)
    assert item.normalized_unit_price is None
    assert item.user_note == "deposit"
    assert Product.objects.filter(pk=auto.pk).exists()  # its mapping still points at it

    update_item(item, line_type=ReceiptItem.LineType.PRODUCT)
    item.refresh_from_db()
    assert (item.match_status, item.product) == (MatchStatus.MATCHED, auto)
    assert item.normalized_unit_price == Decimal("1.2500")


def test_package_change_recomputes_prices(receipt):
    item = milk(receipt)
    update_product(item.product, package_quantity=Decimal("500"), package_unit="ml")
    item.refresh_from_db()
    assert item.normalized_unit_price == Decimal("2.5000")
    update_product(item.product, package_quantity=None, package_unit=None)
    item.refresh_from_db()
    assert (item.normalized_unit, item.normalized_unit_price) == ("piece", Decimal("1.2500"))
    with pytest.raises(ValueError, match="not editable"):
        update_product(item.product, household=None)


def test_merge_moves_lines_and_mappings(member, receipt):
    other = store(member, elsewhere(parsed(), prices={MILK: "1.15"}))
    target, source = milk(receipt).product, milk(other).product
    assert target != source
    update_product(target, package_quantity=Decimal("2"), package_unit="l")

    merge_products(target, [source])
    assert not Product.objects.filter(pk=source.pk).exists()
    moved = milk(other)
    assert moved.product == target
    assert moved.normalized_unit_price == Decimal("0.5750")  # 1.15 for 2 l: target's package
    assert set(target.mappings.values_list("merchant__vat_number", flat=True)) == {
        "094062259",
        "099999999",
    }


@pytest.mark.parametrize("case", ["empty", "self", "foreign"])
def test_merge_validation(member, receipt, case):
    target = milk(receipt).product
    sources = {
        "empty": [],
        "self": [target],
        "foreign": [ProductFactory()],  # another household
    }[case]
    with pytest.raises(ValueError, match=r"other products|same household"):
        merge_products(target, sources)


def test_deleting_a_household_deletes_its_products_and_lines(member, receipt):
    Household.objects.filter(pk=member.household_id).delete()
    assert not Product.objects.exists()
    assert not ReceiptItem.objects.exists()
