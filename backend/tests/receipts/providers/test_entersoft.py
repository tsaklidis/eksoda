"""Entersoft provider: URL recognition, two-step fetch, parser rules, sanitizer."""

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from apps.receipts.errors import FormatChanged, InconsistentSource, ReceiptNotFound
from apps.receipts.fetching import FetchedDocument
from apps.receipts.mydata import DocumentKind, PaymentMethod, Unit
from apps.receipts.providers import registry
from apps.receipts.providers.entersoft.parser import parse_html
from apps.receipts.validation import validate

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "entersoft"
URL = json.loads((FIXTURES / "lidl_21_lines.meta.json").read_text())["url"]
DOC_ID = "00000000-0000-4000-8000-000000000000"


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def identity(url: str = URL):
    return registry.resolve_url(url)[1]


def parse(html: str):
    return parse_html(html, identity())


def document(body: str, status: int = 200) -> FetchedDocument:
    return FetchedDocument(body.encode(), status)


# --- URLs ---------------------------------------------------------------------------
def test_recognition_and_canonical_form():
    provider, ident = registry.resolve_url(URL.replace(DOC_ID, DOC_ID.upper()) + "/")
    assert provider.code == "entersoft"
    assert ident.identity == f"entersoft:{DOC_ID}"
    assert ident.canonical_url == URL
    assert ident.issuer_vat is None  # not in Entersoft URLs


@pytest.mark.parametrize(
    "url",
    [
        "https://e-invoicing.gr/edocuments/ViewInvoice/-1/not-a-uuid_abc12345",
        f"https://e-invoicing.gr/edocuments/ViewInvoice/-1/{DOC_ID}",
        f"https://e-invoicing.gr/edocuments/Other/-1/{DOC_ID}_abc12345",
        f"https://e-invoicing.gr/edocuments/ViewInvoice/-1/{DOC_ID}_abc12345?x=1",
    ],
)
def test_unknown_url_shapes(url):
    from apps.receipts.errors import UnsupportedUrlFormat

    with pytest.raises(UnsupportedUrlFormat):
        registry.resolve_url(url)


# --- two-step fetch ----------------------------------------------------------------
class FakeFetcher:
    def __init__(self, shell: str, doc: FetchedDocument):
        self.shell, self.doc, self.calls = shell, doc, []

    def get(self, url, *, allowed_hosts, accept_statuses=frozenset()):
        self.calls.append((url.geturl(), allowed_hosts, accept_statuses))
        return document(self.shell) if len(self.calls) == 1 else self.doc


def test_fetch_follows_the_document_frame():
    fetcher = FakeFetcher(read("shell.html"), document(read("lidl_21_lines.html")))
    doc = registry.get("entersoft").fetch(identity(), fetcher)
    assert doc.body.decode() == read("lidl_21_lines.html")
    (shell_url, hosts, _), (doc_url, _, statuses) = fetcher.calls
    assert shell_url == URL
    assert hosts == frozenset({"e-invoicing.gr"})
    assert doc_url.startswith("https://e-invoicing.gr/api/GetInvoice?contentType=PEPPOL")
    assert f"intRefDocID={DOC_ID}" in doc_url
    assert statuses == frozenset({418})


def test_fetch_maps_the_418_page_to_not_found():
    fetcher = FakeFetcher(read("shell.html"), document(read("not_found.html"), status=418))
    with pytest.raises(ReceiptNotFound):
        registry.get("entersoft").fetch(identity(), fetcher)
    other = FakeFetcher(read("shell.html"), document("<html>teapot</html>", status=418))
    with pytest.raises(FormatChanged):
        registry.get("entersoft").fetch(identity(), other)


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (lambda s: s.select_one("iframe").decompose(), FormatChanged),
        (
            lambda s: s.select_one("iframe").__setitem__(
                "src", "https://evil.example/api/GetInvoice?a=1"
            ),
            FormatChanged,
        ),
        (
            lambda s: s.select_one("iframe").__setitem__("src", "/api/Other?intRefDocID=x"),
            FormatChanged,
        ),
        (
            lambda s: s.select_one("iframe").__setitem__(
                "src",
                s.select_one("iframe")["src"].replace(
                    DOC_ID, "11111111-1111-4111-8111-111111111111"
                ),
            ),
            InconsistentSource,
        ),
    ],
)
def test_fetch_rejects_unexpected_frames(mutate, error):
    soup = BeautifulSoup(read("shell.html"), "lxml")
    mutate(soup)
    fetcher = FakeFetcher(str(soup), document(read("lidl_21_lines.html")))
    with pytest.raises(error):
        registry.get("entersoft").fetch(identity(), fetcher)
    assert len(fetcher.calls) == 1  # never follows a bad frame


# --- parser -----------------------------------------------------------------------
def test_receipt_values():
    receipt = parse(read("lidl_21_lines.html"))
    assert receipt.issuer.vat_number == "093683423"
    assert receipt.issuer.legal_name == "LIDL"
    assert receipt.branch.address.city == "ΚΟΖΑΝΗΣ"
    assert receipt.branch.address.postal_code == "50100"
    assert receipt.document.kind is DocumentKind.SALE
    assert receipt.document.type_code == "11.1"
    assert (receipt.document.series, receipt.document.number) == ("006604", "789636")
    assert receipt.coverage.issue_time == "approximate"
    assert receipt.coverage.line_tax_amounts is False
    assert receipt.identity.mark == "400014375081554"
    melon = receipt.lines[5]
    assert (melon.quantity, melon.unit, melon.unit_price) == (
        Decimal("2.11"),
        Unit.KG,
        Decimal("1.09"),
    )
    assert (melon.gross_before_discount, melon.discount, melon.gross) == (
        Decimal("2.30"),
        Decimal("0.76"),
        Decimal("1.54"),
    )
    assert melon.unit_label == "ΚΙΛΑ"
    assert receipt.lines[0].unit is Unit.PIECE  # "TEMAXIO" in Latin letters
    assert receipt.lines[12].vat_category_code == "1"  # 24%
    assert receipt.payments[0].method is PaymentMethod.CARD
    assert receipt.totals.discount == Decimal("3.80")
    assert validate(receipt) == []


def test_personal_blocks_are_never_read():
    soup = BeautifulSoup(read("lidl_21_lines.html"), "lxml")
    customer = next(b for b in soup.select(".backgrey") if "ΠΕΛΑΤΗ" in b.get_text())
    for cell in customer.select("div.row > div"):
        cell.string = "SENTINEL-BUYER"
    receipt = parse(str(soup))
    assert "SENTINEL" not in json.dumps(receipt.to_json(), ensure_ascii=False)
    assert "AuthenticationCode" not in json.dumps(receipt.provider_payload)


def _edit(fn):
    soup = BeautifulSoup(read("lidl_21_lines.html"), "lxml")
    fn(soup)
    return str(soup)


def _cell(soup, title, row=0):
    return soup.select("tbody tr")[row].select_one(f'td[data-title="{title}"]')


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda s: setattr(_cell(s, "Συνολική Αξία"), "string", "2,36"), "line totals"),
        (lambda s: setattr(_cell(s, "Έκπτωση"), "string", "1,04"), "line discounts"),
    ],
)
def test_receipt_arithmetic_is_enforced(mutate, message):
    with pytest.raises(InconsistentSource, match=message):
        parse(_edit(mutate))


def test_vat_analysis_must_match_the_totals():
    def mutate(soup):
        block = next(b for b in soup.select(".backgrey") if "ΑΝΑΛΥΣΗ ΦΠΑ" in b.get_text())
        block.select("div.row")[-1].select("div")[-1].string = "2,01EUR"

    with pytest.raises(InconsistentSource, match="VAT analysis"):
        parse(_edit(mutate))


def test_columns_are_found_by_title_not_position():
    def swap(soup):
        for tr in soup.select("tbody tr"):
            cells = tr.find_all("td", recursive=False)
            cells[0].insert_before(copy.copy(cells[-1]))
            cells[-1].decompose()

    receipt = parse(_edit(swap))
    assert receipt.lines[0].gross == Decimal("1.36")
    assert receipt.lines[0].merchant_product_code == "0205084"


def test_header_fallback_when_cells_lose_their_titles():
    def strip_titles(soup):
        for td in soup.select("td[data-title]"):
            if td.find_parent("tr") is not soup.select("tbody tr")[0]:
                continue
            del td["data-title"]

    receipt = parse(_edit(strip_titles))
    assert receipt.lines[0].description == "7DAYS MINI BA.RO150G"


def test_unknown_labels_become_drift_not_errors():
    def mutate(soup):
        _cell(soup, "Μ.Μ.").string = "ΚΙΒΩΤΙΟ"
        soup.select_one(".BoldBlueHeader.fonSize10pt").string = "Νέο Παραστατικό"

    receipt = parse(_edit(mutate))
    assert receipt.lines[0].unit is Unit.OTHER
    assert "unit_label.ΚΙΒΩΤΙΟ" in receipt.unknown_fields
    assert receipt.document.kind is DocumentKind.OTHER
    assert [i.code for i in validate(receipt)] == ["unknown_document_type"]


def test_issue_time_falls_back_to_the_date():
    def mutate(soup):
        row = [r for r in soup.select("div.row") if "διαβίβασης" in r.get_text()][-1]
        row.select("div")[-1].string = "14-07-2026 08:00:00"

    receipt = parse(_edit(mutate))
    assert receipt.coverage.issue_time == "date_only"
    assert receipt.document.issued_at.hour == 0


def test_uid_or_mark_is_required():
    def mutate(soup):
        for row in soup.select("div.row"):
            if row.get_text().strip().startswith(("UID", "M.AR.K")):
                row.decompose()

    with pytest.raises(FormatChanged, match="UID nor MARK"):
        parse(_edit(mutate))


def test_not_found_and_unknown_pages():
    with pytest.raises(ReceiptNotFound):
        parse(read("not_found.html"))
    with pytest.raises(FormatChanged, match="no known layout"):
        parse("<html><body>maintenance</body></html>")


def test_sanitizer_removes_tokens_and_customer_data():
    raw = read("lidl_27_lines.html").replace(DOC_ID, "b0746800-a92c-4ca9-a75e-8389881a2ee1")
    soup = BeautifulSoup(raw, "lxml")
    customer = next(b for b in soup.select(".backgrey") if "ΠΕΛΑΤΗ" in b.get_text())
    customer.select("div.row")[-1].select("div")[-1].string = "Γιώργος Παπαδόπουλος"
    result = registry.get("entersoft").sanitize(str(soup))
    assert "Γιώργος" not in result.html
    assert "b0746800" not in result.html
    assert result.replaced["customer"] == 1


def test_sanitizer_on_the_shell_page():
    real_id, real_token = "b0746800-a92c-4ca9-a75e-8389881a2ee1", "7abc1234"
    raw = read("shell.html").replace(DOC_ID, real_id).replace("0xxx0000", real_token)
    soup = BeautifulSoup(raw, "lxml")
    soup.select_one("[data-download-token]")["data-download-token"] = (
        "1f8e0000-0eda-46a9-9dff-1011da0b8d31"
    )
    soup.body.append(
        BeautifulSoup('<img src="https://e-invoicing.gr/api/CreateBarcode?barcode=x">', "lxml").img
    )
    anchor = soup.select_one('a[href*="mydatapi"]')
    anchor["href"] = "https://mydatapi.aade.gr/myDATA/TimologioQR/QRInfo?q=secret%2ftoken"
    result = registry.get("entersoft").sanitize(str(soup))
    for secret in (real_id, real_token, "1f8e0000", "secret%2ftoken", "barcode=x"):
        assert secret not in result.html
    assert result.replaced == {"download_token": 1, "url_access_token": 2}
    assert "src=" in result.html  # the frame stays usable: it now points to the fake document


def test_rows_wrapping_the_customer_block_are_never_read():
    """An empty last customer field makes the wrapping row's text end with ':'."""

    def mutate(soup):
        customer = next(b for b in soup.select(".backgrey") if "ΠΕΛΑΤΗ" in b.get_text())
        name_row = customer.select("div.row")[-1]
        name_row.select("div")[-1].string = "SENTINEL-BUYER"
        empty = copy.copy(name_row)
        empty.select("div")[0].string = "Διεύθυνση:"
        empty.select("div")[-1].string = ""
        name_row.insert_after(empty)

    receipt = parse(_edit(mutate))
    assert "SENTINEL" not in json.dumps(receipt.to_json(), ensure_ascii=False)


def test_address_with_a_colon_is_kept():
    def mutate(soup):
        header = soup.select_one(".BoldBlueHeader").parent
        address = next(
            d for d in header.find_all("div", recursive=False) if "ΚΟΖΑΝΗΣ" in d.get_text()
        )
        address.string = "ΟΔΟΣ 1, ΤΚ: 50100 ΚΟΖΑΝΗ"

    receipt = parse(_edit(mutate))
    assert receipt.branch.address.street == "ΟΔΟΣ 1, ΤΚ: 50100 ΚΟΖΑΝΗ"
