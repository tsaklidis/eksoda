"""AADE cash-register check page: URL recognition, summary-only parsing, notices."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from apps.receipts.errors import FormatChanged, InconsistentSource, UnsupportedUrlFormat
from apps.receipts.mydata import DocumentKind, PaymentMethod
from apps.receipts.providers import registry
from apps.receipts.providers.aade_fhm.parser import parse_html
from apps.receipts.validation import validate

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "aade_fhm"
URL = json.loads((FIXTURES / "ab_ilion_2024.meta.json").read_text())["url"]


def read(name: str = "ab_ilion_2024.html") -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def parse(html: str, url: str = URL):
    return parse_html(html, registry.resolve_url(url)[1])


def set_record(soup, label: str, value: str) -> None:
    for tr in soup.select("table.info tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) == 2 and cells[0].get_text(strip=True) == label:
            cells[1].string = value
            return
    raise AssertionError(label)


def edited(fn) -> str:
    soup = BeautifulSoup(read(), "lxml")
    fn(soup)
    return str(soup)


def test_recognition():
    provider, identity = registry.resolve_url(URL)
    assert provider.code == "aade_fhm"
    assert identity.identity == "fhm:FGG18025203:00686373"
    assert identity.canonical_url == URL


@pytest.mark.parametrize(
    "query",
    ["SIG=short", "SIG=FGG1802520300686373ABC", "X=1", f"{URL.split('?')[1]}&x=1", ""],
)
def test_unknown_sig_shapes(query):
    with pytest.raises(UnsupportedUrlFormat):
        registry.resolve_url(f"https://www1.aade.gr/tameiakes/myweb/q1.php?{query}")


def test_summary_receipt():
    receipt = parse(read())
    assert receipt.lines == ()
    assert receipt.coverage.line_items is False
    assert receipt.coverage.mydata_registered is False
    assert receipt.identity.source_key == "fhm:FGG18025203:00686373"
    assert receipt.identity.mark is None
    assert receipt.issuer.vat_number == "094025817"
    assert receipt.branch.address.postal_code == "13121"
    assert receipt.branch.address.city == "ΙΛΙΟΝ"
    assert receipt.document.kind is DocumentKind.SALE
    assert receipt.document.type_code is None  # combined label, no single myDATA type
    assert receipt.document.issued_at.isoformat() == "2024-05-17T09:51:00+03:00"
    assert (receipt.totals.net, receipt.totals.vat, receipt.totals.gross) == (
        Decimal("30.38"),
        Decimal("4.55"),
        Decimal("34.93"),
    )
    assert [(e.rate, e.category_code) for e in receipt.vat_breakdown] == [
        (Decimal("13"), "2"),
        (Decimal("24"), "1"),
    ]
    assert validate(receipt) == []


def test_card_and_cash_split():
    receipt = parse(edited(lambda s: set_record(s, "Ποσό πληρωμής με κάρτα", "€ 30.00")))
    card, cash = receipt.payments
    assert (card.method, card.amount, card.derived) == (PaymentMethod.CARD, Decimal("30.00"), False)
    assert (cash.method, cash.amount, cash.derived) == (PaymentMethod.CASH, Decimal("4.93"), True)
    all_card = parse(edited(lambda s: set_record(s, "Ποσό πληρωμής με κάρτα", "€ 34.93")))
    assert [p.method for p in all_card.payments] == [PaymentMethod.CARD]


def test_record_must_match_the_link():
    with pytest.raises(InconsistentSource, match="another receipt"):
        parse(edited(lambda s: set_record(s, "Προοδευτικός α/α", "686374")))
    with pytest.raises(InconsistentSource, match="another receipt"):
        parse(edited(lambda s: set_record(s, "ΦΗΜ", "XYZ18025203")))


def test_amount_mismatch_becomes_a_notice():
    receipt = parse(edited(lambda s: set_record(s, "Συνολική αξία", "€ 35.93")))
    assert "amount_mismatch" in [issue.code for issue in validate(receipt)]


def test_vat_category_rates_are_checked():
    receipt = parse(edited(lambda s: set_record(s, "ΦΠΑ Β", "€ 3.50")))
    codes = [issue.code for issue in validate(receipt)]
    assert "vat_breakdown_rate_mismatch" in codes


def test_buyer_vat_is_never_read_and_is_sanitized():
    html = edited(lambda s: set_record(s, "ΑΦΜ λήπτη (σε τιμολόγιο)", "123456789"))
    receipt = parse(html)
    assert "123456789" not in json.dumps(receipt.to_json())
    result = registry.get("aade_fhm").sanitize(html)
    assert "123456789" not in result.html
    assert result.replaced == {"buyer": 1}


def test_format_problems():
    with pytest.raises(FormatChanged, match="currency"):
        parse(edited(lambda s: set_record(s, "Νόμισμα συναλλαγής", "1# Dollars")))
    with pytest.raises(FormatChanged, match="date"):
        parse(edited(lambda s: set_record(s, "Ημερομηνία, ώρα", "yesterday")))
    with pytest.raises(FormatChanged, match="no known layout"):
        parse("<html><body>maintenance</body></html>")


def test_address_without_postal_code():
    receipt = parse(edited(lambda s: set_record(s, "Διεύθυνση", "ΠΛΑΤΕΙΑ 1")))
    assert receipt.branch.address.street == "ΠΛΑΤΕΙΑ 1"
