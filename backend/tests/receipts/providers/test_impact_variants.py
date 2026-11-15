"""Synthetic variants of the real sample covering formats not seen yet (impact.md §7).

Each variant stays internally consistent, so it must parse without validation
warnings. Replace a variant with a real sanitized receipt when one becomes available.
"""

from decimal import Decimal

from apps.receipts import mydata
from apps.receipts.validation import validate
from tests.receipts.impact import add_line, page, parse, remove_tax_row, set_field, set_tax


def test_credit_note():
    soup = page()
    set_tax(soup, "Είδος Παραστατικού", "11.4")
    set_field(soup, "InvoiceType", "ΠΙΣΤΩΤΙΚΟ ΣΤΟΙΧΕΙΟ ΛΙΑΝΙΚΗΣ")
    receipt = parse(soup)
    assert receipt.document.type_code == "11.4"
    assert mydata.document_kind(receipt.document.type_code) is mydata.DocumentKind.CREDIT_NOTE


def test_cancelled_receipt():
    soup = page()
    set_tax(soup, "Μοναδικός Αριθμός Καταχώρησης Ακυρωτικού", "400015963899999")
    assert parse(soup).identity.cancellation_mark == "400015963899999"


def test_cash_payment():
    soup = page()
    set_tax(soup, "Τύπος Πληρωμής", "3")
    set_field(soup, "PaymentMethodType", "ΜΕΤΡΗΤΑ")
    payment = parse(soup).payments[0]
    assert (payment.method_code, payment.method_label) == ("3", "ΜΕΤΡΗΤΑ")
    assert mydata.payment_method(payment.method_code) is mydata.PaymentMethod.CASH


def test_missing_optional_fields():
    soup = page()
    header_fields = soup.select(".section-header .field")
    for field in header_fields:
        classes = field.get("class", [])
        if "field-TaxOffice" in classes:
            field.decompose()
    for name in ("Street", "City", "Postal", "Country"):
        soup.select(f".section-header .field-{name}")[1].decompose()  # the branch address
    remove_tax_row(soup, "Αρ. Εγκατάστασης")
    receipt = parse(soup)
    assert receipt.branch is None
    assert receipt.issuer.tax_office is None
    assert receipt.issuer.address.city == "ΜΕΤΑΜΟΡΦΩΣΗ"
    assert validate(receipt) == []


def test_carrier_bag_fee_line_at_another_vat_rate():
    soup = page()
    add_line(
        soup,
        code="999001",
        description="ΣΑΚΟΥΛΑ ΜΕΤΑΦΟΡΑΣ",
        unit_code="1",
        unit_label="ΤΕΜΑΧ",
        unit_price=Decimal("0.19"),
        net=Decimal("0.08"),
        vat_code="1",
        vat_rate=24,
        vat=Decimal("0.02"),
        gross=Decimal("0.19"),
        fees=Decimal("0.09"),
    )
    receipt = parse(soup)
    bag = receipt.lines[-1]
    assert bag.fees == Decimal("0.09")
    assert bag.vat_rate == Decimal("24")
    assert receipt.totals.fees == Decimal("0.09")
    assert receipt.totals.gross == Decimal("9.34")
    assert [entry.rate for entry in receipt.vat_breakdown] == [Decimal("13"), Decimal("24")]
    assert validate(receipt) == []


def test_negative_discount_line():
    soup = page()
    add_line(
        soup,
        code="999002",
        description="ΕΚΠΤΩΣΗ ΠΡΟΣΦΟΡΑΣ",
        unit_code="1",
        unit_label="ΤΕΜΑΧ",
        unit_price=Decimal("-0.50"),
        net=Decimal("-0.44"),
        vat_code="2",
        vat_rate=13,
        vat=Decimal("-0.06"),
        gross=Decimal("-0.50"),
    )
    receipt = parse(soup)
    discount = receipt.lines[-1]
    assert (discount.net, discount.vat, discount.gross) == (
        Decimal("-0.44"),
        Decimal("-0.06"),
        Decimal("-0.50"),
    )
    assert receipt.totals.gross == Decimal("8.65")
    assert validate(receipt) == []
