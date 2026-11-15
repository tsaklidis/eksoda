"""Matching lines to household products (requirements §9.2)."""

from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.common.text import normalize_text
from apps.products import matching
from apps.products.matching import match_item, rematch_receipt
from apps.products.models import MerchantProductMapping, Product
from apps.products.review import link_item
from apps.receipts.models import ReceiptItem
from tests.factories import MemberFactory, MerchantFactory, ProductFactory, ReceiptItemFactory
from tests.receipts.importing import (
    LIDL,
    Sample,
    elsewhere,
    page,
    parsed,
    run,
    store,
    submit,
)

pytestmark = pytest.mark.django_db
MatchStatus = ReceiptItem.MatchStatus


@pytest.fixture
def member():
    return MemberFactory()


@pytest.fixture
def merchant():
    return MerchantFactory()


def line(member, description="ΚΟΖΑΝΗΣ ΦΡΕΣΚΟ ΓΑΛΑ ΠΛΗΡΕΣ 1L", code="652432", **kwargs):
    return ReceiptItemFactory.build(
        household=member.household,
        description=description,
        normalized_description=normalize_text(description),
        merchant_product_code=code,
        product=None,
        **kwargs,
    )


def matched(member, merchant, **kwargs) -> ReceiptItem:
    item = line(member, **kwargs)
    match_item(item, merchant=merchant)
    return item


def test_a_new_item_creates_a_product_and_its_mapping(member, merchant):
    item = matched(member, merchant)
    assert item.match_status == MatchStatus.MATCHED
    product = item.product
    assert (product.name, product.household) == ("ΚΟΖΑΝΗΣ ΦΡΕΣΚΟ ΓΑΛΑ ΠΛΗΡΕΣ 1L", member.household)
    assert (product.package_quantity, product.package_unit) == (Decimal("1"), "l")
    assert product.category is None
    mapping = MerchantProductMapping.objects.get()
    assert (mapping.merchant, mapping.merchant_product_code, mapping.product) == (
        merchant,
        "652432",
        product,
    )


def test_a_known_item_matches_and_follows_its_description(member, merchant):
    first = matched(member, merchant).product
    again = matched(member, merchant, description="ΚΟΖΑΝΗΣ ΦΡ. ΓΑΛΑ ΠΛΗΡΕΣ 1L")
    assert (again.match_status, again.product) == (MatchStatus.MATCHED, first)
    assert Product.objects.count() == 1
    mapping = MerchantProductMapping.objects.get()
    assert mapping.last_seen_description == "ΚΟΖΑΝΗΣ ΦΡ. ΓΑΛΑ ΠΛΗΡΕΣ 1L"
    assert mapping.normalized_description == normalize_text("ΚΟΖΑΝΗΣ ΦΡ. ΓΑΛΑ ΠΛΗΡΕΣ 1L")


def test_a_reused_code_goes_to_review(member, merchant):
    milk = matched(member, merchant).product
    paper = matched(member, merchant, description="ΧΑΡΤΙ ΥΓΕΙΑΣ 8ΤΕΜ")
    assert (paper.match_status, paper.product) == (MatchStatus.NEEDS_REVIEW, None)
    mapping = MerchantProductMapping.objects.get()
    assert (mapping.product, mapping.last_seen_description) == (
        milk,
        "ΚΟΖΑΝΗΣ ΦΡΕΣΚΟ ΓΑΛΑ ΠΛΗΡΕΣ 1L",
    )
    assert Product.objects.count() == 1


def test_the_guard_threshold_is_a_setting(member, merchant, settings):
    matched(member, merchant)
    settings.MATCH_GUARD_SIMILARITY = 0.99
    near = matched(member, merchant, description="ΚΟΖΑΝΗΣ ΦΡ. ΓΑΛΑ ΠΛΗΡΕΣ 1L")
    assert near.match_status == MatchStatus.NEEDS_REVIEW


def test_lines_without_a_code_match_on_their_description(member, merchant):
    first = matched(member, merchant, code=None, description="ΚΑΡΠΟΥΖΙ")
    again = matched(member, merchant, code=None, description="Καρπούζι")  # same key
    other = matched(member, merchant, code=None, description="ΠΕΠΟΝΙ")
    assert again.product == first.product
    assert other.product != first.product
    assert MerchantProductMapping.objects.filter(merchant_product_code__isnull=True).count() == 2


def test_items_are_per_merchant_and_per_household(member, merchant):
    first = matched(member, merchant).product
    assert matched(member, MerchantFactory()).product != first
    assert matched(MemberFactory(), merchant).product != first
    assert Product.objects.count() == 3


def test_weighed_lines_get_no_package_size(member, merchant):
    cheese = matched(member, merchant, description="ΤΥΡΙ ΚΕΦΑΛΟΤΥΡΙ 1KG", unit="kg")
    assert cheese.product.package_quantity is None


def test_non_product_lines_are_not_matched(member, merchant):
    fee = matched(member, merchant, description="ΤΕΛΟΣ", line_type=ReceiptItem.LineType.FEE)
    assert (fee.match_status, fee.product) == (MatchStatus.NOT_A_PRODUCT, None)
    assert not Product.objects.exists()


def test_a_lost_race_for_a_new_item_uses_the_winners_mapping(member, merchant, monkeypatch):
    winner = matched(member, merchant).product
    real, calls = matching.find_mapping, []

    def first_lookup_misses(item, merchant):
        calls.append(1)
        return None if len(calls) == 1 else real(item, merchant)

    monkeypatch.setattr(matching, "find_mapping", first_lookup_misses)
    loser = matched(member, merchant)
    assert (loser.match_status, loser.product) == (MatchStatus.MATCHED, winner)
    assert Product.objects.count() == 1  # the loser's product was rolled back


def test_imported_receipt_lines_are_matched_with_prices(member):
    receipt = run(submit(member)).receipt
    items = {item.line_number: item for item in receipt.items.select_related("product")}
    assert {item.match_status for item in items.values()} == {MatchStatus.MATCHED}
    assert [items[n].normalized_unit for n in range(1, 6)] == ["kg", "kg", "piece", "l", "l"]
    assert items[1].normalized_unit_price == Decimal("7.2026")  # 4.48 / 0.622 kg
    assert items[4].normalized_unit_price == Decimal("1.2500")  # 1.25 for 1 l
    assert items[3].product.package_quantity is None  # 27/250ML is ambiguous

    again = store(member, elsewhere(parsed(), vat=receipt.merchant.vat_number, key="3"))
    assert {item.product_id for item in again.items.all()} == {
        item.product_id for item in items.values()
    }
    assert Product.objects.count() == 5


def test_real_lidl_receipt_with_repeated_and_reused_codes(member):
    lidl_27 = Sample(
        "entersoft",
        "lidl_27_lines",
        (page("entersoft", "shell"), page("entersoft", "lidl_27_lines")),
    )
    receipt = store(member, parsed(lidl_27))
    items = {item.line_number: item for item in receipt.items.select_related("product")}
    assert len(items) == 27
    assert {item.match_status for item in items.values()} == {MatchStatus.MATCHED}
    assert items[12].product == items[13].product  # the same code bought twice
    # Two tuna salads under one code (similar enough: LIDL sells them as one item).
    assert items[21].product == items[22].product
    assert items[6].product != items[7].product  # the same coffee under two codes: merge
    assert Product.objects.count() == 25
    fish = items[4].product
    assert (fish.package_quantity, fish.package_unit) == (Decimal("195"), "g")
    assert items[4].normalized_unit == "kg"


def test_rematch_and_backfill_match_only_unlinked_lines(member):
    receipt = store(member, parsed(LIDL))
    # Lines as M3 stored them: no products yet. One line is linked by hand first.
    receipt.items.update(product=None, match_status=MatchStatus.NEEDS_REVIEW)
    MerchantProductMapping.objects.all().delete()
    Product.objects.all().delete()
    chosen = ProductFactory(household=member.household, name="My bread")
    link_item(receipt.items.get(line_number=14), chosen)

    call_command("backfill_matching", household=str(member.household_id))
    items = receipt.items.all()
    assert {item.match_status for item in items} == {MatchStatus.MATCHED}
    assert receipt.items.get(line_number=14).product == chosen
    assert all(item.normalized_unit_price for item in items)
    assert rematch_receipt(receipt) == 0  # nothing left to do
