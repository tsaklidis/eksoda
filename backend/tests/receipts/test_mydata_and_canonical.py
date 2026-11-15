from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from apps.receipts import mydata
from apps.receipts.canonical import Address, Line, Payment, to_jsonable


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        ("11.1", mydata.DocumentKind.SALE),
        ("11.3", mydata.DocumentKind.SALE),
        ("1.1", mydata.DocumentKind.SALE),
        ("11.4", mydata.DocumentKind.CREDIT_NOTE),
        ("5.1", mydata.DocumentKind.CREDIT_NOTE),
        ("17.1", mydata.DocumentKind.OTHER),
        (None, mydata.DocumentKind.OTHER),
    ],
)
def test_document_kind(code, kind):
    assert mydata.document_kind(code) is kind


def test_vat_rates_follow_the_official_table():
    assert mydata.vat_rate("1") == Decimal("24")
    assert mydata.vat_rate("2") == Decimal("13")
    assert mydata.vat_rate("02") == Decimal("13")
    assert mydata.vat_rate("9") == Decimal("3")
    assert mydata.vat_rate("10") == Decimal("4")
    assert mydata.vat_rate("8") is None
    assert mydata.vat_rate("99") is None
    assert mydata.is_known_vat_category("8")
    assert not mydata.is_known_vat_category("99")


def test_units_and_payment_methods():
    assert mydata.measurement_unit("1") is mydata.Unit.PIECE
    assert mydata.measurement_unit("2") is mydata.Unit.KG
    assert mydata.measurement_unit("3") is mydata.Unit.L
    assert mydata.measurement_unit("4") is mydata.Unit.OTHER
    assert mydata.measurement_unit("") is None
    assert mydata.payment_method("7") is mydata.PaymentMethod.CARD
    assert mydata.payment_method("3") is mydata.PaymentMethod.CASH
    assert mydata.payment_method("8") is mydata.PaymentMethod.BANK
    assert mydata.payment_method("42") is mydata.PaymentMethod.OTHER
    assert mydata.payment_method(None) is mydata.PaymentMethod.UNKNOWN


def test_code_normalization():
    assert mydata.normalize_code(" 07 ") == "7"
    assert mydata.normalize_code("11.1") == "11.1"
    assert mydata.normalize_code("  ") is None
    assert mydata.is_absent("0")
    assert mydata.is_absent(None)
    assert not mydata.is_absent("2")


def test_to_jsonable():
    line = Line(line_number=1, description="ΓΑΛΑ", gross=Decimal("1.25"), raw={"a": "b"})
    data = to_jsonable(
        {
            "line": line,
            "when": datetime(2026, 11, 7, 18, 28, tzinfo=UTC),
            "day": date(2026, 11, 7),
            "kind": mydata.DocumentKind.SALE,
            "items": (Payment(amount=Decimal("1")), Address(city="ΚΟΖΑΝΗ")),
        }
    )
    assert data["line"]["gross"] == "1.25"
    assert data["line"]["raw"] == {"a": "b"}
    assert data["when"] == "2026-11-07T18:28:00+00:00"
    assert data["day"] == "2026-11-07"
    assert data["kind"] == "sale"
    assert data["items"][0]["tip"] == "0"
    assert data["items"][1]["city"] == "ΚΟΖΑΝΗ"
