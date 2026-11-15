import copy
import json
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.receipts.errors import FormatChanged, InconsistentSource, ReceiptNotFound
from apps.receipts.fetching import FetchedDocument
from apps.receipts.providers import registry
from apps.receipts.providers.impact import labels
from apps.receipts.providers.impact.parser import PageKind, classify_page
from tests.receipts import impact
from tests.receipts.impact import SAMPLE_URL, UID, page, parse, set_field, set_tax


def test_sample_values():
    r = parse(impact.read())
    assert r.provider_code == "impact"
    assert r.culture == "el"
    assert r.issuer.vat_number == "094062259"
    assert r.issuer.country_code == "GR"
    assert r.issuer.legal_name.startswith("METRO ΑΕΒΕ")
    assert r.issuer.address.city == "ΜΕΤΑΜΟΡΦΩΣΗ"
    assert r.branch.number == "264"
    assert r.branch.address.city == "ΚΟΖΑΝΗ"
    assert r.document.type_code == "11.1"
    assert r.document.formatted_number == "7222-546093"
    assert r.document.issued_at == datetime(2026, 11, 7, 18, 28, tzinfo=ZoneInfo("Europe/Athens"))
    assert r.document.issued_date == date(2026, 11, 7)
    assert r.identity.mark == "400015963897868"
    assert r.identity.uid == UID
    assert r.identity.cancellation_mark is None
    assert (r.totals.net, r.totals.vat, r.totals.gross) == (
        Decimal("8.10"),
        Decimal("1.05"),
        Decimal("9.15"),
    )
    assert len(r.lines) == 5
    first = r.lines[0]
    assert first.merchant_product_code == "127321"
    assert first.quantity == Decimal("0.622")
    assert first.unit_code == "2"
    assert first.unit_label == "ΚΙΛΑ"
    assert first.unit_price == Decimal("7.21")
    assert first.unit_price_basis == "gross"
    assert (first.net, first.vat, first.gross) == (
        Decimal("3.96"),
        Decimal("0.52"),
        Decimal("4.48"),
    )
    assert first.vat_category_code == "2"
    assert first.vat_rate == Decimal("13")
    assert first.line_type_code == "0"
    assert r.payments[0].method_code == "7"
    assert r.payments[0].method_label == "VISA"
    assert r.vat_breakdown[0].category_code == "2"
    assert r.unknown_fields == {}


def test_english_culture_gives_the_same_receipt():
    greek, english = parse(impact.read("sample_el.html")), parse(impact.read("sample_en.html"))
    assert english.culture == "en"
    assert english.document == greek.document
    assert english.totals == greek.totals
    assert [line.gross for line in english.lines] == [line.gross for line in greek.lines]
    assert [line.quantity for line in english.lines] == [line.quantity for line in greek.lines]


def test_payload_is_allowlisted_and_has_no_url():
    r = parse(impact.read())
    assert set(r.provider_payload) == {"commercial", "tax"}
    assert "url" not in r.provider_payload["tax"]["identifiers"]
    assert "0" * 32 not in json.dumps(r.provider_payload)


def test_personal_data_is_never_extracted():
    soup = page()
    for value in soup.select(".CounterParty .value"):
        if not value.select(".value"):
            value.string = "SENTINEL-BUYER"
    set_field(soup, "TransactionId", "SENTINEL-TXN")
    set_field(soup, "Authentication", "SENTINEL-AUTH")
    for label in labels.TAX_DROP:
        for cell in impact.tax_cells(soup, label):
            cell.string = "SENTINEL-TAX"
    # A buyer Party table in the tax view (seen on invoices to businesses).
    issuer_table = soup.select_one(".InvoicesDocDetailed table.Party")
    buyer_table = copy.copy(issuer_table)
    buyer_table.find("h3").string = "Στοιχεία Λήπτη"
    set_tax(buyer_table, "ΑΦΜ", "SENTINEL-BUYER-VAT")
    issuer_table.insert_after(buyer_table)

    receipt = parse(soup)
    assert "SENTINEL" not in json.dumps(receipt.to_json(), ensure_ascii=False)


def test_provider_fetch_and_parse_use_the_document():
    provider = registry.get("impact")
    ident = impact.identity()

    class FakeFetcher:
        def get(self, url, *, allowed_hosts):
            assert url.geturl() == SAMPLE_URL
            assert allowed_hosts == provider.hosts
            return FetchedDocument(impact.read().encode())

    document = provider.fetch(ident, FakeFetcher())
    assert provider.parse(document, ident).totals.gross == Decimal("9.15")


# --- page classification ------------------------------------------------------------
def test_not_found_page():
    assert classify_page(page("not_found.html")) is PageKind.NOT_FOUND
    with pytest.raises(ReceiptNotFound):
        parse(impact.read("not_found.html"))


def test_unknown_page():
    with pytest.raises(FormatChanged, match="no known layout"):
        parse("<html><body><h1>Maintenance</h1></body></html>")


def test_missing_culture_is_a_format_change():
    soup = page()
    del soup.select_one("div.invoice")["data-culture"]
    with pytest.raises(FormatChanged, match="culture"):
        parse(soup)


# --- cross-checks (InconsistentSource) -----------------------------------------------
def _mutated(mutation):
    soup = page()
    mutation(soup)
    return soup


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda s: set_field(s, "NetTotal", "3,97"), "line 1 net"),
        (lambda s: set_field(s, "VATTotal", "0,53"), "line 1 VAT"),
        (lambda s: set_field(s, "Quantity", "0,623"), "line 1 quantity"),
        (
            lambda s: set_field(s.select_one(".section-details"), "Code", "999999"),
            "line 1 item code",
        ),
        (lambda s: set_field(s, "Description1", "OTHER"), "line 1 description"),
        (lambda s: set_field(s, "VatCategory", "24"), "line 1 VAT rate"),
        (lambda s: set_field(s, "TotalGrossValue", "9,16"), "gross total"),
        (lambda s: set_field(s, "Mark", "400015963897869"), "MARK"),
        (lambda s: set_field(s, "Amount", "9,14"), "payment amount"),
        (lambda s: set_tax(s, "Αναγνωριστικό Παραστατικού", "A" * 40), "UID"),
        (lambda s: set_tax(s, "ΑΦΜ", "999999999"), "issuer VAT"),
        (lambda s: set_tax(s, "Κωδ. Χώρας", "CY"), "country"),
        (lambda s: set_tax(s, "Ημερομηνία Έκδοσης", "8/11/2026"), "issue date"),
        (lambda s: set_tax(s, "Νόμισμα", "USD"), "currency"),
        (
            lambda s: set_tax(
                s,
                "Url με το οποίο ο λήπτης του παραστατικού θα μπορεί να το λαμβάνει",
                SAMPLE_URL[:-1] + "1",
            ),
            "URL",
        ),
        (lambda s: s.select(".InvoiceLines")[-1].find_parent("tr").decompose(), "lines"),
    ],
)
def test_views_must_agree(mutation, message):
    with pytest.raises(InconsistentSource, match=message):
        parse(_mutated(mutation))


def test_uid_and_vat_must_match_the_url():
    other_uid = SAMPLE_URL.replace(UID, "B" * 40)
    with pytest.raises(InconsistentSource, match="UID differs from the URL"):
        parse(impact.read(), url=other_uid)
    other_vat = SAMPLE_URL.replace("EL094062259", "EL123456789")
    with pytest.raises(InconsistentSource, match="VAT differs from the URL"):
        parse(impact.read(), url=other_vat)


# --- required fields and formats (FormatChanged) -----------------------------------
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda s: impact.remove_tax_row(s, "Συνολική Αξία"), "summary.gross"),
        (lambda s: impact.remove_tax_row(s, "Είδος Παραστατικού"), "type_code"),
        (lambda s: impact.remove_tax_row(s, "Αναγνωριστικό Παραστατικού"), "uid"),
        (lambda s: impact.remove_tax_row(s, "Καθαρή Αξία"), "line 1 net"),
        (lambda s: s.select_one(".field-DateIssued").decompose(), "DateIssued"),
        (lambda s: s.select_one("td.field-Total").decompose(), "line 1 total"),
        (lambda s: set_field(s, "Quantity", "0,6,22"), "line 1"),
        (lambda s: set_field(s, "DateIssued", "yesterday"), "date"),
        (lambda s: set_tax(s, "Ημερομηνία Έκδοσης", "31/02/2026"), "date"),
        (lambda s: set_tax(s, "ΑΑ Γραμμής", "first"), "line number"),
        (lambda s: _remove_all_lines(s), "no lines"),
    ],
)
def test_required_fields_and_formats(mutation, message):
    with pytest.raises(FormatChanged, match=message):
        parse(_mutated(mutation))


def _remove_all_lines(soup):
    for div in soup.select(".InvoiceLines"):
        div.find_parent("tr").decompose()
    for tr in soup.select(".section-details tbody tr"):
        tr.decompose()


def test_missing_mark_needs_the_transmission_failure_flag():
    soup = page()
    set_tax(soup, "Μοναδικός Αριθμός Καταχώρησης Παραστατικού", "")
    set_field(soup, "Mark", "")
    with pytest.raises(FormatChanged, match="MARK"):
        parse(soup)
    set_tax(soup, "Αδυναμία Επικοινωνίας Παρόχου", "1", prefix=True)
    receipt = parse(soup)
    assert receipt.identity.mark is None
    assert receipt.identity.transmission_failure is True


def test_a_new_layout_is_reached_for_a_changed_page(monkeypatch):
    """Only the not-found page is decided before the layouts (requirements §7.4)."""
    from apps.receipts.providers.impact import parser as impact_parser

    class RenamedLayout:
        name = "impact/2"

        def matches(self, soup):
            return soup.select_one("div.receipt-v2") is not None

        def parse(self, soup, identity):
            return "parsed by v2"

    monkeypatch.setattr(impact_parser, "LAYOUTS", (RenamedLayout(), *impact_parser.LAYOUTS))
    html = "<html><body><div class='receipt-v2'>new format</div></body></html>"
    assert impact_parser.parse_html(html, impact.identity()) == "parsed by v2"
    assert parse(impact.read()).parser_version == "impact/1"  # old pages still use v1
