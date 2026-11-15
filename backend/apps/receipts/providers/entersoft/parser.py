"""Entersoft receipt document → CanonicalReceipt (docs/providers/entersoft.md).

Single rendering (no tax view to cross-check), so the parser enforces the
receipt's own arithmetic as fatal consistency checks (Σ lines = total, VAT
analysis = net/VAT totals, Σ discounts = discount total) and leaves per-line
arithmetic to validation warnings. Fields are located by labels and data-title
attributes, not positions, so reordered columns keep working.
"""

import re
from datetime import datetime, time
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from apps.common.numbers import DateFormatError, parse_date, parse_local_datetime
from apps.receipts import vocabulary
from apps.receipts.canonical import (
    Address,
    Branch,
    CanonicalReceipt,
    Coverage,
    Document,
    Identity,
    Line,
    Party,
    Payment,
    Totals,
    VatEntry,
)
from apps.receipts.errors import FormatChanged, InconsistentSource, ReceiptNotFound
from apps.receipts.links import ParsedUrl
from apps.receipts.mydata import Unit
from apps.receipts.providers.base import UrlIdentity, parse_with_layouts
from apps.receipts.providers.entersoft.urls import (
    DOCUMENT_PATH,
    HOST,
    PROVIDER_CODE,
    EntersoftLink,
)
from apps.receipts.providers.html import amount, child_cells, key_of, label_map, required, text_of

PARSER_VERSION = "entersoft/1"
CULTURE = "el"
SOURCE_TZ = ZoneInfo("Europe/Athens")
TOLERANCE = Decimal("0.02")
NOT_FOUND_MARKER = "Page not found"

ITEM_COLUMNS = {  # td[data-title] → key
    "Κωδικός": "code",
    "Περιγραφή": "description",
    "Μ.Μ.": "unit",
    "Ποσότητα": "quantity",
    "Τιμή μονάδας": "unit_price",
    "Αξία προ έκπτωσης": "before_discount",
    "Έκπτωση": "discount",
    "ΦΠΑ%": "vat_rate",
    "Συνολική Αξία": "gross",
}
ITEM_HEADERS = {  # thead th → key (fallback when cells lack data-title)
    "ΚΩΔΙΚΟΣ": "code",
    "ΠΕΡΙΓΡΑΦΗ": "description",
    "ΜΜ": "unit",
    "ΠΟΣΟΤΗΤΑ": "quantity",
    "ΤΙΜΗ ΜΟΝ.": "unit_price",
    "ΑΞΙΑ ΠΡΟ ΕΚΠΤ.": "before_discount",
    "ΕΚΠΤ.": "discount",
    "ΦΠΑ%": "vat_rate",
    "ΣΥΝΟΛΙΚΗ ΑΞΙΑ": "gross",
}
HEADER_FIELDS = {"Α.Φ.Μ": "vat", "Αρ. Παραστατικού": "number", "Ημ/νία έκδοσης": "issue_date"}
TOTAL_LABELS = {
    "Αξία προ έκπτωσης": "before_discount",
    "Έκπτωση": "discount",
    "ΤΕΛΙΚΗ ΑΞΙΑ": "gross",
    "Καθαρή Αξία": "net",
    "Φ.Π.Α": "vat",
}
REMARK_LABELS = {
    "Πάροχος": "provider",
    "Url πάροχου": "provider_url",
    "Άδεια καταλληλότητας (ΥΠΑΗΕΣ)": "license",
    "UID": "uid",
    "M.AR.K": "mark",
    "Ημ/νία διαβίβασης": "transmitted_at",
}
REMARK_DROP = frozenset({key_of("AuthenticationCode")})  # provider signature: never read
# Titled blocks. The parser never reads the customer block (personal data); the
# sanitizer replaces its values.
CUSTOMER_BLOCK = key_of("ΣΤΟΙΧΕΙΑ ΠΕΛΑΤΗ")
VAT_BLOCK = key_of("ΑΝΑΛΥΣΗ ΦΠΑ")
PAYMENT_BLOCK = key_of("ΣΤΟΙΧΕΙΑ ΠΛΗΡΩΜΗΣ")
_HEADER_LINE = re.compile(r"^([^:]{2,40}):\s*(\S.*)$")
_NUMBER = re.compile(r"^(?P<series>.+)-(?P<number>\d+)$")
_ADDRESS = re.compile(
    r"^(?P<street>[^,]+),\s*(?P<number>[^,]*),\s*(?P<postal>\d{5}),\s*(?P<city>.+)$"
)


# --- fetching helpers -----------------------------------------------------------------
def is_not_found(html: str) -> bool:
    return NOT_FOUND_MARKER in html


def document_url_from_shell(html: str, link: EntersoftLink) -> ParsedUrl:
    """The receipt document framed by the shell page; it must be the same document."""
    soup = BeautifulSoup(html, "lxml")
    frame = soup.select_one("iframe#iframeContent") or soup.find("iframe", src=True)
    if frame is None or not frame.get("src"):
        raise FormatChanged("the page has no document frame")
    parts = urlsplit(frame["src"])
    if (parts.scheme, parts.netloc) not in (
        ("", ""),
        ("https", HOST),
    ) or parts.path != DOCUMENT_PATH:
        raise FormatChanged("the document frame points to an unexpected address")
    params = parse_qs(parts.query)
    document_id = (params.get("intRefDocID") or [""])[0].lower()
    token = (params.get("hashToken") or [""])[0]
    if document_id != link.document_id or token != link.token:
        raise InconsistentSource("the document frame points to another document")
    return ParsedUrl(scheme="https", host=HOST, port=None, path=parts.path, query=parts.query)


# --- layout -----------------------------------------------------------------------
class EntersoftLayoutV1:
    """Receipt rendering as observed 2026-11-14 (LIDL retail receipts)."""

    name = PARSER_VERSION

    def matches(self, soup: BeautifulSoup) -> bool:
        return (
            bool(soup.select("table td[data-title]"))
            and soup.select_one(".BoldBlueHeader") is not None
        )

    def parse(self, soup: BeautifulSoup, identity: UrlIdentity) -> CanonicalReceipt:
        return _Builder(soup, identity).build()


LAYOUTS = (EntersoftLayoutV1(),)


def parse_html(html: str, identity: UrlIdentity) -> CanonicalReceipt:
    if is_not_found(html):
        raise ReceiptNotFound("the provider shows its page-not-found message")
    return parse_with_layouts(BeautifulSoup(html, "lxml"), identity, LAYOUTS)


class _Builder:
    def __init__(self, soup: BeautifulSoup, identity: UrlIdentity):
        self.soup = soup
        self.url = identity
        self.unknown: dict[str, str] = {}
        self.blocks = self._titled_blocks()
        self.blocked = {id(tag) for block in self.blocks.values() for tag in block.find_all(True)}
        # Elements wrapping a titled block (e.g. the row that holds the customer block) are
        # not free rows either: their text includes the block's, possibly personal, content.
        self.wrapping = {id(parent) for block in self.blocks.values() for parent in block.parents}

    def num(self, text: str | None, where: str) -> Decimal | None:
        return amount(text, CULTURE, where)

    # --- structure ------------------------------------------------------------------
    def _titled_blocks(self) -> dict[str, Tag]:
        blocks = {}
        for block in self.soup.select(".backgrey"):
            title = block.select_one(".BoldBlueHeader")
            if title is not None:
                blocks.setdefault(key_of(text_of(title)), block)
        return blocks

    def _free_rows(self) -> list[list[str]]:
        """Cell texts of div.row elements neither inside nor around the titled blocks."""
        rows = []
        for row in self.soup.select("div.row"):
            if id(row) in self.blocked or id(row) in self.wrapping:
                continue
            cells = child_cells(row)
            if len(cells) == 2:
                rows.append([text_of(cell) for cell in cells])
        return rows

    def _block_rows(self, title_key: str, width: int) -> list[list[str]]:
        block = self.blocks.get(title_key)
        if block is None:
            return []
        rows = []
        for row in block.select("div.row"):
            if "BoldBlueHeader" in (row.get("class") or []):
                continue
            cells = [text_of(cell) for cell in child_cells(row)]
            # Column-header rows carry no digits in their value cell.
            if len(cells) == width and any(ch.isdigit() for ch in cells[-1]):
                rows.append(cells)
        return rows

    # --- sections ------------------------------------------------------------------
    def header(self) -> dict[str, str]:
        name_element = self.soup.select_one(".BoldBlueHeader")
        info = {"name": text_of(name_element)}
        lines = [
            text_of(div)
            for div in name_element.parent.find_all("div", class_="fontSize8pt", recursive=False)
        ]
        info["address"] = next((line for line in lines if line and not _is_header_field(line)), "")
        pairs = []
        for div in self.soup.select("div.fontSize8pt"):
            if id(div) in self.blocked:
                continue
            match = _HEADER_LINE.match(text_of(div))
            if match:
                pairs.append((match.group(1), match.group(2)))
                if key_of(match.group(1)) == key_of("Αρ. Παραστατικού"):
                    title = div.find_previous_sibling("div", class_="BoldBlueHeader")
                    info["title"] = text_of(title)
        values, _unknown = label_map(pairs, HEADER_FIELDS)
        info.update(values)
        return info

    def items(self) -> list[dict[str, str]]:
        table = next((t for t in self.soup.select("table") if t.select("td[data-title]")), None)
        headers = [key_of(text_of(th)) for th in table.select("thead th")]
        by_title = {key_of(label): key for label, key in ITEM_COLUMNS.items()}
        by_header = {key_of(label): key for label, key in ITEM_HEADERS.items()}
        rows = []
        for tr in table.select("tbody tr"):
            row = {}
            for position, td in enumerate(tr.find_all("td", recursive=False)):
                title = td.get("data-title") or ""
                key = by_title.get(key_of(title)) if title else None
                if key is None and position < len(headers):
                    key = by_header.get(headers[position])
                if key is None:
                    self.unknown[f"item.{title or position}"] = text_of(td)
                    continue
                row[key] = text_of(td)
            if row:
                rows.append(row)
        return rows

    def remarks(self, free_rows: list[list[str]]) -> dict[str, str]:
        pairs = [
            (label, value)
            for label, value in free_rows
            if label.endswith(":") and key_of(label) not in REMARK_DROP
        ]
        values, unknown = label_map(pairs, REMARK_LABELS)
        self.unknown.update({f"remark.{label}": value for label, value in unknown.items()})
        return values

    # --- build ----------------------------------------------------------------------
    def build(self) -> CanonicalReceipt:
        header = self.header()
        free_rows = self._free_rows()
        remarks = self.remarks(free_rows)
        totals_raw, _unknown = label_map(free_rows, TOTAL_LABELS)
        lines = self.lines()
        totals = self.totals(totals_raw)
        breakdown = self.vat_breakdown()
        self.check_consistency(lines, totals, breakdown)
        document, issue_time = self.document(header, remarks, totals_raw)

        uid = (remarks.get("uid") or "").upper() or None
        mark = remarks.get("mark") or None
        if uid is None and mark is None:
            raise FormatChanged("neither UID nor MARK on the page")
        vat_number = re.sub(r"\D", "", required(header, "vat", "issuer VAT"))
        return CanonicalReceipt(
            provider_code=PROVIDER_CODE,
            parser_version=PARSER_VERSION,
            culture=CULTURE,
            source_url=self.url.canonical_url,
            issuer=Party(
                country_code="GR",
                vat_number=vat_number,
                legal_name=required(header, "name", "merchant name"),
            ),
            branch=_branch(header.get("address")),
            document=document,
            identity=Identity(uid=uid, mark=mark),
            totals=totals,
            lines=lines,
            vat_breakdown=breakdown,
            payments=self.payments(),
            coverage=Coverage(
                line_items=True,
                line_tax_amounts=False,
                official_codes=False,
                mydata_registered=True,
                issue_time=issue_time,
                cross_checked=False,
            ),
            provider_payload={"header": header, "remarks": remarks, "totals": totals_raw},
            unknown_fields=self.unknown,
        )

    def document(self, header, remarks, totals_raw) -> tuple[Document, str]:
        title = header.get("title") or None
        code, kind = vocabulary.document_type(title)
        if code is None:
            self.unknown["document.type_label"] = title or ""
        try:
            issued_date = parse_date(required(header, "issue_date", "issue date"), "dmy")
            transmitted = remarks.get("transmitted_at")
            transmitted_at = (
                parse_local_datetime(transmitted, culture=CULTURE, order="dmy", tz=SOURCE_TZ)
                if transmitted
                else None
            )
        except DateFormatError as exc:
            raise FormatChanged(str(exc)) from exc
        # The page prints only the issue date. The myDATA transmission time, when it is on
        # the same day, is the best available time of purchase.
        if transmitted_at is not None and transmitted_at.date() == issued_date:
            issued_at, issue_time = transmitted_at, "approximate"
        else:
            issued_at, issue_time = datetime.combine(issued_date, time.min, SOURCE_TZ), "date_only"

        # The currency is printed only as a suffix of the total, e.g. "75,48EUR".
        gross_text = required(totals_raw, "gross", "total")
        currency = vocabulary.currency(re.sub(r"[\d.,\s-]", "", gross_text))
        if currency is None:
            raise FormatChanged("missing currency on the total")
        number_text = header.get("number") or ""
        number_match = _NUMBER.match(number_text)
        return (
            Document(
                kind=kind,
                type_code=code,
                type_label=title,
                series=number_match["series"] if number_match else None,
                number=number_match["number"] if number_match else (number_text or None),
                formatted_number=number_text or None,
                issued_at=issued_at,
                issued_date=issued_date,
                currency=currency,
            ),
            issue_time,
        )

    def lines(self) -> tuple[Line, ...]:
        rows = self.items()
        if not rows:
            raise FormatChanged("the receipt has no item rows")
        lines = []
        for index, row in enumerate(rows, start=1):
            where = f"line {index}"
            unit_label = row.get("unit") or None
            unit = vocabulary.unit(unit_label)
            if unit is None and unit_label:
                self.unknown[f"unit_label.{unit_label}"] = unit_label
                unit = Unit.OTHER
            rate = self.num(row.get("vat_rate"), where)
            unit_price = self.num(row.get("unit_price"), where)
            lines.append(
                Line(
                    line_number=index,
                    description=row.get("description", ""),
                    gross=self.num(required(row, "gross", f"{where} total"), where),
                    quantity=self.num(row.get("quantity"), where),
                    unit=unit,
                    unit_label=unit_label,
                    unit_price=unit_price,
                    unit_price_basis="gross" if unit_price is not None else "unknown",
                    gross_before_discount=self.num(row.get("before_discount"), where),
                    discount=self.num(row.get("discount"), where),
                    vat_rate=rate,
                    vat_category_code=vocabulary.vat_category_for_rate(rate),
                    merchant_product_code=row.get("code") or None,
                    raw={f"item.{key}": value for key, value in row.items()},
                )
            )
        return tuple(lines)

    def totals(self, raw: dict[str, str]) -> Totals:
        return Totals(
            gross=self.num(required(raw, "gross", "total"), "total"),
            net=self.num(raw.get("net"), "net total"),
            vat=self.num(raw.get("vat"), "VAT total"),
            gross_before_discount=self.num(raw.get("before_discount"), "total before discount"),
            discount=self.num(raw.get("discount"), "discount total"),
        )

    def vat_breakdown(self) -> tuple[VatEntry, ...]:
        entries = []
        for rate_text, net_text, vat_text in self._block_rows(VAT_BLOCK, 3):
            rate = self.num(rate_text, "VAT analysis")
            entries.append(
                VatEntry(
                    rate=rate,
                    category_code=vocabulary.vat_category_for_rate(rate),
                    net=self.num(net_text, "VAT analysis"),
                    vat=self.num(vat_text, "VAT analysis"),
                )
            )
        return tuple(entries)

    def payments(self) -> tuple[Payment, ...]:
        payments = []
        for label, amount_text in self._block_rows(PAYMENT_BLOCK, 2):
            method = vocabulary.payment_method(label)
            if method is None:
                self.unknown[f"payment_label.{label}"] = label
            payments.append(
                Payment(amount=self.num(amount_text, "payment"), method=method, method_label=label)
            )
        return tuple(payments)

    @staticmethod
    def check_consistency(lines, totals: Totals, breakdown) -> None:
        def off(a: Decimal, b: Decimal | None) -> bool:
            return b is not None and abs(a - b) > TOLERANCE

        if off(sum((line.gross for line in lines), Decimal(0)), totals.gross):
            raise InconsistentSource("the line totals do not add up to the receipt total")
        discounts = [line.discount for line in lines if line.discount is not None]
        if discounts and off(sum(discounts, Decimal(0)), totals.discount):
            raise InconsistentSource("the line discounts do not add up to the discount total")
        if breakdown:
            if off(sum((entry.net for entry in breakdown), Decimal(0)), totals.net):
                raise InconsistentSource("the VAT analysis does not add up to the net total")
            if off(sum((entry.vat for entry in breakdown), Decimal(0)), totals.vat):
                raise InconsistentSource("the VAT analysis does not add up to the VAT total")


def _branch(address: str | None) -> Branch | None:
    if not address:
        return None
    match = _ADDRESS.match(address)
    if not match:
        return Branch(address=Address(street=address))
    number = match["number"].strip()
    return Branch(
        address=Address(
            street=match["street"].strip(),
            number=None if number in ("", "-") else number,
            postal_code=match["postal"],
            city=match["city"].strip(),
        )
    )


_HEADER_FIELD_KEYS = frozenset(key_of(label) for label in HEADER_FIELDS)


def _is_header_field(line: str) -> bool:
    """A known "Label: value" header line (VAT, number, date), as opposed to an address."""
    match = _HEADER_LINE.match(line)
    return bool(match) and key_of(match.group(1)) in _HEADER_FIELD_KEYS
