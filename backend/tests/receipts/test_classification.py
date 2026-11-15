from decimal import Decimal

import pytest

from apps.receipts.canonical import Line
from apps.receipts.classification import LineType, classify
from apps.receipts.models import ReceiptItem
from apps.receipts.providers import registry
from tests.receipts.importing import IMPACT, LIDL, fetched, page, url


def line(description: str, gross: str = "1.00", **amounts) -> Line:
    values = {key: Decimal(value) for key, value in amounts.items()}
    return Line(line_number=1, description=description, gross=Decimal(gross), **values)


@pytest.mark.parametrize(
    ("description", "gross", "amounts", "expected"),
    [
        ("ΓΑΛΑ ΦΡΕΣΚΟ 1L", "1.50", {}, LineType.PRODUCT),
        ("ΕΚΠΤΩΣΗ ΚΑΡΤΑΣ", "-0.50", {}, LineType.DISCOUNT),
        ("Έκπτωση μέλους", "-0.50", {}, LineType.DISCOUNT),  # accents and case
        ("ΚΟΥΠΟΝΙ ΠΡΟΣΦΟΡΑΣ", "-1.00", {}, LineType.DISCOUNT),
        ("Discount 10%", "-1.00", {}, LineType.DISCOUNT),
        ("ΕΠΙΣΤΡΟΦΗ ΕΙΔΟΥΣ", "-2.00", {}, LineType.OTHER),  # negative, not a discount
        ("ΕΚΠΤΩΣΗ ΠΟΣΟΤΗΤΑΣ", "0.00", {}, LineType.DISCOUNT),
        ("ΠΕΡΙΒΑΛΛΟΝΤΙΚΟ ΤΕΛΟΣ ΣΑΚΟΥΛΑΣ", "0.10", {}, LineType.FEE),
        ("Περιβαλλοντικό τέλος", "0.09", {}, LineType.FEE),
        ("ΕΓΓΥΗΣ ΦΙΑΛΗΣ", "0.10", {}, LineType.FEE),
        ("ΣΑΚΟΥΛ.ΒΙΟΔ.25Μ1ΤΕΜ", "0.99", {}, LineType.PRODUCT),  # bags are products
        ("S.ΣΑΚΟΥΛΕΣ 60L 20Τ", "2.49", {}, LineType.PRODUCT),
        ("ΤΕΛΟΣ ΑΝΑΚΥΚΛΩΣΗΣ", "0.04", {"net": "0", "fees": "0.04"}, LineType.FEE),
        ("ΦΟΡΟΣ ΔΙΑΜΟΝΗΣ", "1.50", {"net": "0", "other_taxes": "1.50"}, LineType.FEE),
        ("ΔΩΡΟ", "0.00", {"net": "0"}, LineType.PRODUCT),  # zero, but no fee either
        ("ΤΕΛΟΣ", "0.04", {"fees": "0.04"}, LineType.PRODUCT),  # net unknown
    ],
)
def test_classify(description, gross, amounts, expected):
    assert classify(line(description, gross, **amounts)) is expected


def test_keywords_match_whole_word_starts_in_order():
    assert classify(line("ΤΕΛΟΣ ΠΕΡΙΒΑΛΛΟΝΤΙΚΟ")) is LineType.PRODUCT  # wrong order
    assert classify(line("ΑΝΤΙΕΚΠΤΩΣΗ")) is LineType.PRODUCT  # not at a word start


def test_fixture_receipts_have_only_product_lines():
    lidl_27 = (page("entersoft", "lidl_27_lines"), url("entersoft", "lidl_27_lines"))
    pages = [(IMPACT.pages[0], IMPACT.url), (LIDL.pages[1], LIDL.url), lidl_27]
    for html, receipt_url in pages:
        provider, identity = registry.resolve_url(receipt_url)
        receipt = provider.parse(fetched(html), identity)
        assert {classify(item) for item in receipt.lines} == {LineType.PRODUCT}


def test_model_choices_match_the_classifier():
    assert {choice.value for choice in ReceiptItem.LineType} == {t.value for t in LineType}
