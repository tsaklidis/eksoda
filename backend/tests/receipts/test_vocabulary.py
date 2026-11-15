from decimal import Decimal

import pytest

from apps.receipts import vocabulary
from apps.receipts.mydata import DocumentKind, PaymentMethod, Unit


@pytest.mark.parametrize(
    ("label", "code", "kind"),
    [
        ("Απόδειξη Λιανικής Πώλησης", "11.1", DocumentKind.SALE),
        ("ΑΠΟΔΕΙΞΗ ΛΙΑΝΙΚΗΣ ΠΩΛΗΣΗΣ", "11.1", DocumentKind.SALE),
        ("ΑΛΠ (Απόδειξη Λιανικής Πώλησης)", "11.1", DocumentKind.SALE),
        ("Πιστωτικό Στοιχ. Λιανικής", "11.4", DocumentKind.CREDIT_NOTE),
        ("ΑΠΟΔΕΙΞΗ ΠΑΡΟΧΗΣ ΥΠΗΡΕΣΙΩΝ - ΑΠΟΔΕΙΞΗ ΛΙΑΝΙΚΗΣ ΠΩΛΗΣΗΣ", None, DocumentKind.SALE),
        ("Πιστωτικό Τιμολόγιο", None, DocumentKind.CREDIT_NOTE),
        ("Δελτίο Αποστολής", None, DocumentKind.OTHER),
        (None, None, DocumentKind.OTHER),
    ],
)
def test_document_type(label, code, kind):
    assert vocabulary.document_type(label) == (code, kind)


@pytest.mark.parametrize(
    ("label", "unit"),
    [
        ("TEMAXIO", Unit.PIECE),  # Latin letters
        ("ΤΕΜΑΧΙΟ", Unit.PIECE),  # Greek letters
        ("ΤΕΜΑΧ", Unit.PIECE),
        ("ΚΙΛΑ", Unit.KG),
        ("kg", Unit.KG),
        ("ΛΙΤΡΑ", Unit.L),
        ("ΚΙΒΩΤΙΟ", None),
        ("", None),
    ],
)
def test_units(label, unit):
    assert vocabulary.unit(label) is unit


def test_payment_methods_and_currency():
    assert vocabulary.payment_method("POS / e-POS") is PaymentMethod.CARD
    assert vocabulary.payment_method("VISA") is PaymentMethod.CARD
    assert vocabulary.payment_method("ΜΕΤΡΗΤΑ") is PaymentMethod.CASH
    assert vocabulary.payment_method("bitcoin") is None
    assert vocabulary.currency("EUR") == "EUR"
    assert vocabulary.currency("€") == "EUR"
    assert vocabulary.currency("0# Euro Member Countries") == "EUR"
    assert vocabulary.currency("usd") == "USD"
    assert vocabulary.currency("") is None
    assert vocabulary.currency("1# Dollars") is None


def test_vat_category_for_rate():
    assert vocabulary.vat_category_for_rate(Decimal("24")) == "1"
    assert vocabulary.vat_category_for_rate(Decimal("13")) == "2"
    assert vocabulary.vat_category_for_rate(Decimal("4")) is None  # categories 6 and 10
    assert vocabulary.vat_category_for_rate(None) is None


@pytest.mark.parametrize(
    ("label", "kind"),
    [
        ("ΑΠΟΔΕΙΞΗ ΕΠΙΣΤΡΟΦΗΣ", DocumentKind.CREDIT_NOTE),
        ("Απόδειξη Επιστροφής Χρημάτων", DocumentKind.CREDIT_NOTE),
        ("ΑΚΥΡΩΤΙΚΟ ΑΠΟΔΕΙΞΗΣ", DocumentKind.OTHER),
    ],
)
def test_returns_and_cancellations_are_not_sales(label, kind):
    assert vocabulary.document_type(label) == (None, kind)
