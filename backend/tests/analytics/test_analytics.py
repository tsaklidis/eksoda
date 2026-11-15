"""Spending analytics (requirements §12.9, §13)."""

import random
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.analytics import queries
from apps.analytics.periods import Period, add_months, month_period, months_ending
from apps.products.models import ProductCategory
from apps.receipts.models import Receipt, ReceiptItem
from tests.factories import (
    MerchantFactory,
    ProductFactory,
    ReceiptFactory,
    ReceiptItemFactory,
)
from tests.receipts.importing import AADE, IMPACT, LIDL, parsed, store
from tests.utils import error_code

pytestmark = pytest.mark.django_db
ATHENS = ZoneInfo("Europe/Athens")
NOVEMBER = {"from": "2026-11-01", "to": "2026-11-30"}
LineType = ReceiptItem.LineType


def url(name: str) -> str:
    return reverse(f"api-v1:analytics-{name}")


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=ATHENS)


def category(slug: str) -> ProductCategory:
    return ProductCategory.objects.get(household=None, slug=slug)


def receipt(member, total, when="2026-11-10T12:00", lines=(), merchant=None, **kwargs):
    """A receipt with lines given as (line type, gross, product or None)."""
    made = ReceiptFactory(
        household=member.household,
        merchant=merchant or MerchantFactory(),
        issued_at=at(when),
        gross_total=Decimal(total),
        **kwargs,
    )
    for number, (line_type, gross, product) in enumerate(lines, start=1):
        ReceiptItemFactory(
            receipt=made,
            line_number=number,
            line_type=line_type,
            gross_amount=Decimal(gross),
            product=product,
            match_status=(
                "matched"
                if product
                else "needs_review"
                if line_type == "product"
                else "not_a_product"
            ),
        )
    return made


# --- periods ---------------------------------------------------------------------------
def test_periods():
    november = month_period(date(2026, 11, 14))
    assert (str(november.first), str(november.last), november.days) == (
        "2026-11-01",
        "2026-11-30",
        30,
    )
    previous = november.previous()
    assert (str(previous.first), str(previous.last)) == ("2026-10-02", "2026-10-31")
    assert str(add_months(date(2026, 1, 1), -1)) == "2025-12-01"
    year = months_ending(date(2026, 11, 14), 12)
    assert (str(year.first), str(year.last)) == ("2025-12-01", "2026-11-30")
    start, end = Period(year.first, year.first).bounds(ATHENS)
    assert (start.isoformat(), end.isoformat()) == (
        "2025-12-01T00:00:00+02:00",
        "2025-12-02T00:00:00+02:00",
    )


# --- summary ---------------------------------------------------------------------------
def test_summary(owner, owner_client):
    receipt(owner, "100.00")
    receipt(owner, "50.00")
    receipt(owner, "30.00", document_kind=Receipt.Kind.CREDIT_NOTE)
    receipt(owner, "999.00", status=Receipt.Status.CANCELLED)  # not counted
    receipt(owner, "999.00", excluded_from_analytics=True)  # not counted
    receipt(owner, "999.00", currency="USD")  # not added to euros
    receipt(owner, "60.00", when="2026-10-20T12:00")  # previous period (Oct 2–31)
    ReceiptItemFactory(receipt=receipt(owner, "0.00", when="2025-01-01T00:00"))  # needs review

    body = owner_client.get(url("summary"), NOVEMBER).json()
    assert body["currency"] == "EUR"
    current = body["current"]
    assert current["period"] == {"from": "2026-11-01", "to": "2026-11-30"}
    assert current["spending"] == "120.00"  # 100 + 50 − 30
    assert (current["receipt_count"], current["sales_count"]) == (3, 2)
    assert (current["average_sale"], current["credit_notes_total"]) == ("75.00", "30.00")
    assert current["other_currency_receipts"] == 1
    assert body["previous"] == {
        "period": {"from": "2026-10-02", "to": "2026-10-31"},
        "spending": "60.00",
    }
    assert body["change"] == {"amount": "60.00", "percent": "100.00"}
    assert body["needs_review_count"] == 1


def test_summary_without_previous_spending(owner, owner_client):
    receipt(owner, "10.00")
    body = owner_client.get(url("summary"), NOVEMBER).json()
    assert body["change"] == {"amount": "10.00", "percent": None}
    empty = owner_client.get(url("summary"), {"from": "2020-01-01", "to": "2020-01-31"}).json()
    assert (empty["current"]["spending"], empty["current"]["average_sale"]) == ("0.00", None)


def test_default_period_is_the_current_month(owner, owner_client):
    ReceiptFactory(household=owner.household, issued_at=timezone.now(), gross_total=Decimal(7))
    body = owner_client.get(url("summary")).json()
    today = timezone.localdate(timezone=ATHENS)
    assert body["current"]["period"]["from"] == today.replace(day=1).isoformat()
    assert body["current"]["spending"] == "7.00"
    only_from = owner_client.get(url("summary"), {"from": "2026-11-01"}).json()
    assert only_from["current"]["period"]["to"] == max(today.isoformat(), "2026-11-01")
    only_to = owner_client.get(url("summary"), {"to": "2026-11-20"}).json()
    assert only_to["current"]["period"] == {"from": "2026-11-01", "to": "2026-11-20"}


@pytest.mark.parametrize(
    ("name", "params"),
    [
        ("summary", {"from": "2026-11-10", "to": "2026-11-01"}),
        ("summary", {"from": "yesterday"}),
        ("monthly-trend", {"months": 0}),
        ("monthly-trend", {"months": 37}),
        ("top-products", {"by": "price"}),
        ("top-products", {"limit": 51}),
    ],
)
def test_invalid_parameters(owner_client, name, params):
    response = owner_client.get(url(name), params)
    assert (response.status_code, error_code(response)) == (400, "validation_error")


# --- by merchant ---------------------------------------------------------------------------
def test_spending_by_merchant(owner, owner_client):
    metro, lidl = MerchantFactory(display_name="Metro"), MerchantFactory(display_name="Lidl")
    receipt(owner, "20.00", merchant=metro)
    receipt(owner, "15.00", merchant=metro)
    receipt(owner, "40.00", merchant=lidl)
    receipt(owner, "5.00", merchant=lidl, document_kind=Receipt.Kind.CREDIT_NOTE)

    body = owner_client.get(url("spending-by-merchant"), NOVEMBER).json()
    assert body["total"] == "70.00"
    rows = [
        (row["merchant"]["display_name"], row["total"], row["receipts"])
        for row in body["merchants"]
    ]
    assert rows == [("Lidl", "35.00", 2), ("Metro", "35.00", 2)]  # ties by name


# --- by category ---------------------------------------------------------------------------
def buckets(client, params=NOVEMBER) -> dict[str, str]:
    body = client.get(url("spending-by-category"), params).json()
    totals = {row["name"]: row["total"] for row in body["buckets"]}
    assert sum(Decimal(total) for total in totals.values()) == Decimal(body["total"])
    return totals


def test_every_line_goes_to_one_bucket(owner, owner_client):
    dairy = ProductFactory(household=owner.household, category=category("dairy-and-eggs"))
    plain = ProductFactory(household=owner.household)
    grocer = MerchantFactory(default_category=category("groceries"))
    receipt(
        owner,
        "20.00",
        merchant=grocer,
        lines=[
            (LineType.PRODUCT, "6.00", dairy),  # its own category
            (LineType.PRODUCT, "10.00", plain),  # the merchant's default category
            (LineType.DISCOUNT, "-1.00", None),
            (LineType.FEE, "0.50", None),
            (LineType.OTHER, "-0.50", None),
        ],
    )  # lines add up to 15.00: 5.00 left for the merchant's default category
    receipt(owner, "8.00", lines=[(LineType.PRODUCT, "8.00", plain)])  # no default: uncategorized
    receipt(owner, "35.00")  # summary-only, no default category
    fuel = MerchantFactory(default_category=category("fuel-and-transport"))
    receipt(owner, "50.00", merchant=fuel)  # summary-only

    assert buckets(owner_client) == {
        "Fuel and transport": "50.00",
        "Unallocated": "35.00",
        "Groceries": "15.00",
        "Uncategorized": "8.00",
        "Dairy and eggs": "6.00",
        "Fees and deposits": "0.50",
        "Other adjustments": "-0.50",
        "Discounts": "-1.00",
    }
    body = owner_client.get(url("spending-by-category"), NOVEMBER).json()
    assert body["total"] == "113.00"
    fuel_row = body["buckets"][0]
    assert fuel_row["bucket"] == "category"
    assert fuel_row["category"]["slug"] == "fuel-and-transport"
    assert fuel_row["share"] == "44.25"
    unallocated = body["buckets"][1]
    assert (unallocated["bucket"], unallocated["category"]) == ("unallocated", None)


def test_credit_notes_count_negative_in_their_buckets(owner, owner_client):
    product = ProductFactory(household=owner.household, category=category("beverages"))
    receipt(owner, "10.00", lines=[(LineType.PRODUCT, "10.00", product)])
    receipt(
        owner,
        "4.00",
        lines=[(LineType.PRODUCT, "4.00", product)],
        document_kind=Receipt.Kind.CREDIT_NOTE,
    )
    assert buckets(owner_client) == {"Beverages": "6.00"}


def test_merchant_default_category_applies_to_past_receipts(owner, owner_client):
    shop = MerchantFactory()
    receipt(owner, "12.00", merchant=shop, lines=[(LineType.PRODUCT, "12.00", None)])
    receipt(owner, "30.00", merchant=shop)
    assert buckets(owner_client) == {"Unallocated": "30.00", "Uncategorized": "12.00"}
    shop.default_category = category("pharmacy-and-health")
    shop.save()
    assert buckets(owner_client) == {"Pharmacy and health": "42.00"}


def test_real_receipts_add_up(owner, owner_client):
    for sample in (IMPACT, LIDL, AADE):
        stored = store(owner, parsed(sample))
        Receipt.objects.filter(pk=stored.pk).update(issued_at=at("2026-11-05T10:00"))
    totals = buckets(owner_client)
    assert Decimal(sum(Decimal(v) for v in totals.values())) == Decimal(
        "119.56"
    )  # 9.15+75.48+34.93


def test_bucket_sum_invariant_on_random_receipts(owner):
    rng = random.Random(7)
    categories = [None, category("bakery"), category("groceries")]
    merchants = [MerchantFactory(default_category=rng.choice(categories)) for _ in range(4)]
    products = [
        ProductFactory(household=owner.household, category=rng.choice(categories)) for _ in range(5)
    ]
    for index in range(40):
        lines = [
            (
                rng.choice(list(LineType)),
                f"{rng.uniform(-3, 30):.2f}",
                None,
            )
            for _ in range(rng.randrange(0, 6))
        ]
        lines = [
            (kind, gross, rng.choice(products) if kind == LineType.PRODUCT else None)
            for kind, gross, _ in lines
        ]
        receipt(
            owner,
            f"{rng.uniform(0, 120):.2f}",
            when=f"2026-11-{rng.randrange(1, 31):02d}T{rng.randrange(24):02d}:00",
            lines=lines,
            merchant=rng.choice(merchants),
            document_kind=rng.choice([Receipt.Kind.SALE] * 5 + [Receipt.Kind.CREDIT_NOTE]),
            mark=f"7{index:014d}",
        )
    period = Period(date(2026, 11, 1), date(2026, 11, 30))
    breakdown = queries.spending_by_category(owner.household, period)
    assert sum(bucket.total for bucket in breakdown.buckets) == breakdown.spending
    assert breakdown.spending == queries.totals(owner.household, period).spending


# --- monthly trend ----------------------------------------------------------------------
def test_monthly_trend_uses_household_months(owner, owner_client):
    receipt(owner, "10.00", when="2026-11-30T23:30")  # 21:30 UTC: still November in Athens
    receipt(owner, "20.00", when="2026-12-01T00:30")  # 22:30 UTC on Nov 30: December
    receipt(owner, "5.00", when="2026-09-15T09:00")
    body = owner_client.get(url("monthly-trend"), {"to": "2026-12-05", "months": 4}).json()
    assert body["period"] == {"from": "2026-09-01", "to": "2026-12-31"}
    assert [(row["month"], row["total"], row["receipts"]) for row in body["months"]] == [
        ("2026-09-01", "5.00", 1),
        ("2026-10-01", "0.00", 0),
        ("2026-11-01", "10.00", 1),
        ("2026-12-01", "20.00", 1),
    ]
    november = owner_client.get(url("summary"), NOVEMBER).json()
    assert november["current"]["spending"] == "10.00"


def test_monthly_trend_defaults_to_twelve_months(owner_client):
    body = owner_client.get(url("monthly-trend")).json()
    assert len(body["months"]) == 12


# --- top products -------------------------------------------------------------------------
def test_top_products(owner, owner_client):
    milk = ProductFactory(household=owner.household, name="Γάλα")
    oil = ProductFactory(household=owner.household, name="Λάδι")
    for _ in range(3):
        receipt(owner, "1.30", lines=[(LineType.PRODUCT, "1.30", milk)])
    receipt(owner, "9.50", lines=[(LineType.PRODUCT, "9.50", oil)])
    receipt(  # credit notes are not purchases
        owner,
        "9.50",
        lines=[(LineType.PRODUCT, "9.50", oil)],
        document_kind=Receipt.Kind.CREDIT_NOTE,
    )
    for item in ReceiptItem.objects.all():
        from apps.products.prices import refresh_prices

        refresh_prices([item])

    by_count = owner_client.get(url("top-products"), NOVEMBER).json()
    assert by_count["by"] == "count"
    rows = [(row["product"]["name"], row["receipts"], row["spend"]) for row in by_count["products"]]
    assert rows == [("Γάλα", 3, "3.90"), ("Λάδι", 1, "9.50")]
    by_spend = owner_client.get(url("top-products"), NOVEMBER | {"by": "spend", "limit": 1}).json()
    assert [row["product"]["name"] for row in by_spend["products"]] == ["Λάδι"]


# --- households and query counts -------------------------------------------------------------
def test_other_households_never_count(owner, owner_client, outsider):
    receipt(outsider, "500.00")
    body = owner_client.get(url("summary"), NOVEMBER).json()
    assert body["current"]["spending"] == "0.00"


@pytest.mark.parametrize(
    ("name", "limit"),
    [
        ("summary", 7),
        ("spending-by-category", 8),
        ("spending-by-merchant", 5),
        ("monthly-trend", 5),
        ("top-products", 5),
    ],
)
def test_query_counts_do_not_grow_with_data(
    owner, owner_client, django_assert_max_num_queries, name, limit
):
    product = ProductFactory(household=owner.household, category=category("bakery"))
    for _ in range(10):
        receipt(owner, "3.00", lines=[(LineType.PRODUCT, "3.00", product)])
    with django_assert_max_num_queries(limit):
        assert owner_client.get(url(name), NOVEMBER).status_code == 200
