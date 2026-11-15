from decimal import Decimal

import pytest

from apps.products.prices import PRICE_HISTORY, normalize, refresh_product_prices
from apps.receipts.models import Receipt, ReceiptItem
from tests.factories import ProductFactory, ReceiptFactory, ReceiptItemFactory

Unit = ReceiptItem.Unit


def line(quantity="1", unit=Unit.PIECE, gross="2.00", line_type=ReceiptItem.LineType.PRODUCT):
    return ReceiptItemFactory.build(
        quantity=None if quantity is None else Decimal(quantity),
        unit=unit,
        gross_amount=Decimal(gross),
        line_type=line_type,
    )


def product(quantity=None, unit=None):
    return ProductFactory.build(
        package_quantity=None if quantity is None else Decimal(quantity), package_unit=unit
    )


@pytest.mark.parametrize(
    ("item", "package", "expected"),
    [
        # weighed: the measured quantity, whatever the package
        (line("0.622", Unit.KG, "4.48"), product("1", "kg"), ("0.622000", "kg", "7.2026")),
        (line("1.5", Unit.L, "3.00"), product(), ("1.500000", "l", "2.0000")),
        # pieces with a package size: per kg or l
        (line("2", Unit.PIECE, "3.00"), product("500", "g"), ("1.000000", "kg", "3.0000")),
        (line("1", Unit.PIECE, "1.25"), product("1", "l"), ("1.000000", "l", "1.2500")),
        (line("3", Unit.PIECE, "1.68"), product("330", "ml"), ("0.990000", "l", "1.6970")),
        (line("1", Unit.PIECE, "4.00"), product("6", "piece"), ("6.000000", "piece", "0.6667")),
        # pieces without a package size: per piece
        (line("3", Unit.PIECE, "1.68"), product(), ("3.000000", "piece", "0.5600")),
        # other units: per that unit, kept apart
        (line("2", Unit.OTHER, "5.00"), product("1", "kg"), ("2.000000", "other", "2.5000")),
        (line("2", None, "5.00"), product(), ("2.000000", "other", "2.5000")),
    ],
)
def test_normalize(item, package, expected):
    quantity, unit, price = normalize(item, package)
    assert (quantity, unit, price) == (Decimal(expected[0]), expected[1], Decimal(expected[2]))


@pytest.mark.parametrize(
    ("item", "package"),
    [
        (line(None), product()),  # unknown quantity
        (line("1", line_type=ReceiptItem.LineType.FEE), product()),  # not a product line
        (line("1"), None),  # no product
    ],
)
def test_no_price_without_the_inputs(item, package):
    assert normalize(item, package) == (None, None, None)


def test_zero_quantity_has_no_price():
    quantity, unit, price = normalize(line("0"), product())
    assert (quantity, unit, price) == (Decimal(0), "piece", None)


@pytest.mark.django_db
def test_price_history_filter():
    owned = ProductFactory()

    def entry(receipt=None, **kwargs):
        receipt = receipt or ReceiptFactory(household=owned.household)
        item = ReceiptItemFactory(receipt=receipt, product=owned, match_status="matched", **kwargs)
        refresh_product_prices(owned)
        return item

    counted = entry()
    entry(ReceiptFactory(household=owned.household, status=Receipt.Status.CANCELLED))
    entry(ReceiptFactory(household=owned.household, document_kind=Receipt.Kind.CREDIT_NOTE))
    entry(quantity=Decimal(0))
    entry(gross_amount=Decimal(0))
    assert list(ReceiptItem.objects.filter(PRICE_HISTORY)) == [counted]
