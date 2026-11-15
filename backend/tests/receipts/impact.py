"""Helpers for Impact fixtures: loading, parsing and building synthetic variants.

Variants are made by editing the sanitized real sample, so they keep the real page
structure. Editing helpers write values in the Greek (el) culture format.
"""

import copy
from decimal import Decimal
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from apps.common.numbers import parse_decimal
from apps.common.text import collapse_whitespace
from apps.receipts.canonical import CanonicalReceipt
from apps.receipts.providers import registry
from apps.receipts.providers.impact.parser import parse_html

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "impact"
GOLDEN = FIXTURES / "expected"
UID = "FA8355776160C1AF53AC6A860C29C0BB1437029F"
SAMPLE_URL = f"https://einvoice.impact.gr/p/EL094062259/{UID}/{'0' * 32}"


def read(name: str = "sample_el.html") -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def page(name: str = "sample_el.html") -> BeautifulSoup:
    return BeautifulSoup(read(name), "lxml")


def identity(url: str = SAMPLE_URL):
    return registry.resolve_url(url)[1]


def parse(source: str | BeautifulSoup, url: str = SAMPLE_URL) -> CanonicalReceipt:
    return parse_html(str(source), identity(url))


# --- editing helpers ---------------------------------------------------------------
def el(value: Decimal) -> str:
    return f"{value:.2f}".replace(".", ",")


def tax_cells(soup: BeautifulSoup | Tag, label: str, *, prefix: bool = False) -> list[Tag]:
    """Value cells of tax-view rows with this label (the commercial view is excluded:
    its summary rows also have two cells and some identical labels)."""
    root = soup.select_one(".InvoicesDocDetailed") or soup
    cells = []
    for tr in root.select("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) != 2:
            continue
        text = collapse_whitespace(tds[0].get_text(" ", strip=True))
        if text == label or (prefix and text.startswith(label)):
            cells.append(tds[1])
    return cells


def set_tax(
    soup: BeautifulSoup | Tag, label: str, value: str, nth: int = 0, *, prefix: bool = False
) -> None:
    tax_cells(soup, label, prefix=prefix)[nth].string = value


def remove_tax_row(soup: BeautifulSoup, label: str) -> None:
    tax_cells(soup, label)[0].find_parent("tr").decompose()


def set_field(soup: BeautifulSoup | Tag, name: str, value: str, nth: int = 0) -> None:
    soup.select(f".field-{name} .value")[nth].string = value


def _bump(element: Tag, delta: Decimal) -> None:
    element.string = el(parse_decimal(element.get_text(strip=True), "el") + delta)


def add_line(
    soup: BeautifulSoup,
    *,
    code: str,
    description: str,
    unit_code: str,
    unit_label: str,
    unit_price: Decimal,
    net: Decimal,
    vat_code: str,
    vat_rate: int,
    vat: Decimal,
    gross: Decimal,
    fees: Decimal = Decimal("0"),
) -> None:
    """Append a consistent line to both views and update every total."""
    rows = soup.select(".section-details tbody tr")
    row = copy.copy(rows[-1])
    rows[-1].insert_after(row)
    commercial = {
        "Code": code,
        "Description1": description,
        "Quantity": "1,00",
        "MeasurementUnit": unit_label,
        "UnitPrice": el(unit_price),
        "NetTotal": el(net),
        "VatCategory": str(vat_rate),
        "VATTotal": el(vat),
        "Total": el(gross),
    }
    for name, value in commercial.items():
        set_field(row, name, value)

    line_rows = [div.find_parent("tr") for div in soup.select(".InvoiceLines")]
    tax_row = copy.copy(line_rows[-1])
    line_rows[-1].insert_after(tax_row)
    tax = {
        "ΑΑ Γραμμής": str(len(line_rows) + 1),
        "Κωδικός Είδους": code,
        "Περιγραφή Είδους": description,
        "Ποσότητα": "1,0",
        "Είδος Ποσότητας": unit_code,
        "Καθαρή Αξία": el(net),
        "Κατηγορία ΦΠΑ": vat_code,
        "Ποσό ΦΠΑ": el(vat),
        "Ποσό Τελών": el(fees),
    }
    for label, value in tax.items():
        set_tax(tax_row, label, value)

    for name, delta in (
        ("TotalNetAmount", net),
        ("TotalVATAmount", vat),
        ("TotalGrossValue", gross),
    ):
        _bump(soup.select_one(f".field-{name} .value"), delta)
    for label, delta in (
        ("Σύνολο Καθαρής Αξίας", net),
        ("Σύνολο ΦΠΑ", vat),
        ("Σύνολο Τελών", fees),
        ("Συνολική Αξία", gross),
        ("Αναλογούν Ποσό", gross),
    ):
        _bump(tax_cells(soup, label)[0], delta)
    _bump(soup.select_one(".section-paymentanalysis .field-Amount .value"), gross)

    breakdown = soup.select(".section-taxes tbody tr")
    for vat_row in breakdown:
        if (
            parse_decimal(vat_row.select_one(".field-Percentage .value").get_text(strip=True), "el")
            == vat_rate
        ):
            _bump(vat_row.select_one(".field-UnderlyingValue .value"), net)
            _bump(vat_row.select_one(".field-VatAmount .value"), vat)
            return
    vat_row = copy.copy(breakdown[-1])
    breakdown[-1].insert_after(vat_row)
    set_field(vat_row, "Percentage", f"{vat_rate},00%")
    set_field(vat_row, "UnderlyingValue", el(net))
    set_field(vat_row, "VatAmount", el(vat))
