"""Impact receipt page → CanonicalReceipt (docs/providers/impact.md §6, TD §9.5).

Both views of the page are read and cross-checked. Identifiers, codes and amounts
come from the tax (myDATA) view; unit price, unit label, VAT %, names, addresses
and the time of day come from the commercial view. Any disagreement fails the
import (InconsistentSource); a missing required field fails it as FormatChanged.
"""

from collections.abc import Mapping
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from apps.common.numbers import (
    CULTURES,
    DateFormatError,
    parse_date,
    parse_local_datetime,
)
from apps.common.text import collapse_whitespace
from apps.receipts import mydata, vocabulary
from apps.receipts.canonical import (
    Address,
    Branch,
    CanonicalReceipt,
    Document,
    Identity,
    Line,
    Party,
    Payment,
    Totals,
    VatEntry,
)
from apps.receipts.errors import FormatChanged, InconsistentSource, ReceiptNotFound
from apps.receipts.providers.base import UrlIdentity, parse_with_layouts
from apps.receipts.providers.html import amount, required
from apps.receipts.providers.impact import labels
from apps.receipts.providers.impact.urls import PROVIDER_CODE
from apps.receipts.providers.impact.views import (
    CommercialView,
    TaxView,
    extract_commercial,
    extract_tax_view,
)

PARSER_VERSION = "impact/1"
SOURCE_TZ = ZoneInfo("Europe/Athens")
# Date order per (culture, view). With the "en" culture the tax view switches to
# month/day while the commercial view stays day/month (observed 2026-11-14).
DATE_ORDER = {
    ("el", "commercial"): "dmy",
    ("el", "tax"): "dmy",
    ("en", "commercial"): "dmy",
    ("en", "tax"): "mdy",
}


class PageKind(StrEnum):
    RECEIPT = "receipt"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


def classify_page(soup: BeautifulSoup) -> PageKind:
    if soup.select_one("div.invoice") and soup.select_one("div.InvoicesDocDetailed"):
        return PageKind.RECEIPT
    if labels.NOT_FOUND_MARKER in soup.get_text(" "):
        return PageKind.NOT_FOUND
    return PageKind.UNKNOWN


class ImpactLayoutV1:
    """The page as observed 2026-11-13: commercial view + myDATA tax view."""

    name = PARSER_VERSION

    def matches(self, soup: BeautifulSoup) -> bool:
        return classify_page(soup) is PageKind.RECEIPT

    def parse(self, soup: BeautifulSoup, identity: UrlIdentity) -> CanonicalReceipt:
        invoice = soup.select_one("div.invoice")
        culture = invoice.get("data-culture")
        if culture not in CULTURES:
            raise FormatChanged(f"unknown page culture {culture!r}")
        commercial = extract_commercial(invoice)
        tax = extract_tax_view(soup.select_one("div.InvoicesDocDetailed"))
        return _Builder(commercial, tax, culture, identity).build()


# Newest first. A changed page format gets a new layout; old ones stay for old fixtures.
LAYOUTS = (ImpactLayoutV1(),)


def parse_html(html: str, identity: UrlIdentity) -> CanonicalReceipt:
    soup = BeautifulSoup(html, "lxml")
    # Only the not-found page is decided here; recognizing receipt structure is each
    # layout's job (matches()), so a new layout can handle a changed page.
    if classify_page(soup) is PageKind.NOT_FOUND:
        raise ReceiptNotFound("the provider shows its document-not-found page")
    return parse_with_layouts(soup, identity, LAYOUTS)


class _Builder:
    def __init__(self, commercial: CommercialView, tax: TaxView, culture: str, url: UrlIdentity):
        self.c = commercial
        self.t = tax
        self.culture = culture
        self.url = url

    # --- helpers ------------------------------------------------------------------
    def num(self, text: str | None, where: str) -> Decimal | None:
        return amount(text, self.culture, where)

    def required_num(self, mapping: Mapping[str, str], key: str, where: str) -> Decimal:
        return self.num(required(mapping, key, where), where)

    @staticmethod
    def agree(a, b, what: str) -> None:
        """Both views must agree whenever both provide a value."""
        if a is not None and b is not None and a != b:
            raise InconsistentSource(f"{what} differs between the commercial and tax views")

    # --- build ----------------------------------------------------------------------
    def build(self) -> CanonicalReceipt:
        identity = self.identity()
        document = self.document()
        lines = self.lines()
        return CanonicalReceipt(
            provider_code=PROVIDER_CODE,
            parser_version=PARSER_VERSION,
            culture=self.culture,
            source_url=self.url.canonical_url,
            issuer=self.issuer(),
            branch=self.branch(),
            document=document,
            identity=identity,
            totals=self.totals(),
            lines=lines,
            vat_breakdown=self.vat_breakdown(lines),
            payments=self.payments(),
            provider_payload=self.payload(),
            unknown_fields={**self.c.unknown, **self.t.unknown},
        )

    def identity(self) -> Identity:
        uid = required(self.t.identifiers, "uid", "tax.uid").upper()
        self.agree((self.c.certification.get("Uid") or "").upper() or None, uid, "UID")
        if uid != self.url.uid:
            raise InconsistentSource("the page UID differs from the URL")

        tax_vat = required(self.t.issuer, "vat", "tax.issuer.vat")
        commercial_vat = (self.c.issuer.get("Vat") or "").upper()
        # The commercial view may print the VAT with its country prefix ("EL094062259").
        commercial_vat = commercial_vat[2:] if commercial_vat[:2].isalpha() else commercial_vat
        self.agree(commercial_vat or None, tax_vat, "issuer VAT")
        if tax_vat != self.url.issuer_vat:
            raise InconsistentSource("the page issuer VAT differs from the URL")
        country = self.t.issuer.get("country")
        if country and country.upper() != self.url.issuer_country:
            raise InconsistentSource("the page issuer country differs from the URL")
        page_url = self.t.identifiers.get("url")
        if page_url and page_url.rstrip("/").upper() != self.url.canonical_url.upper():
            raise InconsistentSource("the receipt URL printed on the page differs")

        failure = (self.t.identifiers.get("transmission_failure") or "0").strip() == "1"
        mark = (
            None if mydata.is_absent(self.t.identifiers.get("mark")) else self.t.identifiers["mark"]
        )
        commercial_mark = self.c.certification.get("Mark") or None
        self.agree(commercial_mark, mark, "MARK")
        if mark is None and not failure:
            raise FormatChanged("missing MARK without a transmission-failure flag")
        cancellation = self.t.identifiers.get("cancellation_mark")
        return Identity(
            uid=uid,
            mark=mark,
            cancellation_mark=None if mydata.is_absent(cancellation) else cancellation,
            transmission_failure=failure,
        )

    def document(self) -> Document:
        tax_date_text = required(self.t.header, "issue_date", "tax.issue_date")
        commercial_text = required(self.c.identity, "DateIssued", "commercial.DateIssued")
        try:
            issued_date = parse_date(tax_date_text, DATE_ORDER[(self.culture, "tax")])
            issued_at = parse_local_datetime(
                commercial_text,
                culture=self.culture,
                order=DATE_ORDER[(self.culture, "commercial")],
                tz=SOURCE_TZ,
            )
        except DateFormatError as exc:
            raise FormatChanged(str(exc)) from exc
        if issued_at.date() != issued_date:
            raise InconsistentSource("issue date differs between the commercial and tax views")

        currency = self.t.header.get("currency") or self.c.summary.get("CurrencyCode")
        self.agree(self.c.summary.get("CurrencyCode"), self.t.header.get("currency"), "currency")
        if not currency:
            raise FormatChanged("missing required field currency")
        type_code = required(self.t.header, "type_code", "tax.type_code")
        return Document(
            kind=mydata.document_kind(type_code),
            type_code=type_code,
            type_label=self.c.identity.get("InvoiceType") or None,
            series=self.t.header.get("series") or None,
            number=self.t.header.get("number") or None,
            formatted_number=self.c.identity.get("IssuerFormatedInvoiceSeriesNumber") or None,
            issued_at=issued_at,
            issued_date=issued_date,
            currency=currency.upper(),
        )

    def issuer(self) -> Party:
        info = self.c.issuer
        return Party(
            country_code=self.url.issuer_country,
            vat_number=self.url.issuer_vat,
            legal_name=required(info, "RegisteredName", "commercial.RegisteredName"),
            activity=info.get("Activities") or None,
            tax_office=info.get("TaxOffice") or None,
            gemi_number=info.get("GeneralCommercialRegistryNumber") or None,
            address=_address(self.c.head_office),
        )

    def branch(self) -> Branch | None:
        number = self.t.issuer.get("branch") or None
        address = _address(self.c.branch)
        if number is None and address is None:
            return None
        return Branch(number=number, address=address)

    def lines(self) -> tuple[Line, ...]:
        if len(self.c.lines) != len(self.t.lines):
            raise InconsistentSource(
                f"{len(self.c.lines)} commercial lines but {len(self.t.lines)} tax lines"
            )
        if not self.t.lines:
            raise FormatChanged("the receipt has no lines")
        return tuple(
            self.line(index, c, t)
            for index, (c, t) in enumerate(zip(self.c.lines, self.t.lines, strict=True), start=1)
        )

    def line(self, index: int, c: Mapping[str, str], t: Mapping[str, str]) -> Line:
        where = f"line {index}"
        net = self.required_num(t, "net", f"{where} net")
        vat = self.required_num(t, "vat", f"{where} VAT")
        gross = self.required_num(c, "Total", f"{where} total")
        self.agree(self.num(c.get("NetTotal"), where), net, f"{where} net")
        self.agree(self.num(c.get("VATTotal"), where), vat, f"{where} VAT")

        quantity = self.num(t.get("quantity"), where)
        self.agree(self.num(c.get("Quantity"), where), quantity, f"{where} quantity")
        quantity = quantity if quantity is not None else self.num(c.get("Quantity"), where)

        code = t.get("code") or None
        self.agree(c.get("Code") or None, code, f"{where} item code")
        description = collapse_whitespace(t.get("description") or "")
        commercial_description = collapse_whitespace(c.get("Description1") or "")
        self.agree(commercial_description or None, description or None, f"{where} description")

        category = mydata.normalize_code(t.get("vat_category"))
        rate = self.num(c.get("VatCategory"), where)
        if mydata.is_known_vat_category(category):
            self.agree(rate, mydata.vat_rate(category), f"{where} VAT rate")
            rate = mydata.vat_rate(category)

        unit_price = self.num(c.get("UnitPrice"), where)
        line_number = t.get("line_number") or str(index)
        if not line_number.isdigit():
            raise FormatChanged(f"{where}: line number {line_number!r}")
        return Line(
            line_number=int(line_number),
            description=description or commercial_description,
            gross=gross,
            quantity=quantity,
            unit=mydata.measurement_unit(t.get("unit_code")),
            unit_code=mydata.normalize_code(t.get("unit_code")),
            unit_label=c.get("MeasurementUnit") or None,
            unit_price=unit_price,
            # Impact prints VAT-inclusive unit prices (0.622 kg × 7.21 = 4.48 gross).
            unit_price_basis="gross" if unit_price is not None else "unknown",
            net=net,
            vat_category_code=category,
            vat_rate=rate,
            vat=vat,
            withheld=self.num(t.get("withheld"), where),
            fees=self.num(t.get("fees"), where),
            other_taxes=self.num(t.get("other_taxes"), where),
            stamp_duty=self.num(t.get("stamp_duty"), where),
            digital_fee=self.num(t.get("digital_fee"), where),
            deductions=self.num(t.get("deductions"), where),
            merchant_product_code=code or (c.get("Code") or None),
            line_type_code=mydata.normalize_code(t.get("line_type_code")),
            annotation_code=mydata.normalize_code(t.get("detail_type")),
            vat_exemption_code=mydata.normalize_code(t.get("vat_exemption")),
            raw={
                **{f"commercial.{key}": value for key, value in c.items()},
                **{f"tax.{key}": value for key, value in t.items()},
            },
        )

    def totals(self) -> Totals:
        s = self.t.summary
        gross = self.required_num(s, "gross", "tax.summary.gross")
        net, vat = self.num(s.get("net"), "summary"), self.num(s.get("vat"), "summary")
        self.agree(self.num(self.c.summary.get("TotalGrossValue"), "summary"), gross, "gross total")
        self.agree(self.num(self.c.summary.get("TotalNetAmount"), "summary"), net, "net total")
        self.agree(self.num(self.c.summary.get("TotalVATAmount"), "summary"), vat, "VAT total")
        return Totals(
            gross=gross,
            net=net,
            vat=vat,
            withheld=self.num(s.get("withheld"), "summary"),
            fees=self.num(s.get("fees"), "summary"),
            other_taxes=self.num(s.get("other_taxes"), "summary"),
            stamp_duty=self.num(s.get("stamp_duty"), "summary"),
            digital_fee=self.num(s.get("digital_fee"), "summary"),
            deductions=self.num(s.get("deductions"), "summary"),
        )

    def vat_breakdown(self, lines: tuple[Line, ...]) -> tuple[VatEntry, ...]:
        code_by_rate = {line.vat_rate: line.vat_category_code for line in lines}
        entries = []
        for row in self.c.vat_breakdown:
            rate = self.num(row.get("Percentage"), "VAT breakdown")
            entries.append(
                VatEntry(
                    rate=rate,
                    category_code=code_by_rate.get(rate),
                    net=self.required_num(row, "UnderlyingValue", "VAT breakdown net"),
                    vat=self.required_num(row, "VatAmount", "VAT breakdown amount"),
                )
            )
        return tuple(entries)

    def payments(self) -> tuple[Payment, ...]:
        # Tax-view payments are authoritative. Commercial rows are paired with them by
        # position, and only when both views list the same number of payments.
        if self.t.payments:
            same_count = len(self.c.payments) == len(self.t.payments)
            commercial_rows = self.c.payments if same_count else [{}] * len(self.t.payments)
            payments = []
            for row, commercial in zip(self.t.payments, commercial_rows, strict=True):
                paid = self.required_num(row, "amount", "payment amount")
                self.agree(self.num(commercial.get("Amount"), "payment"), paid, "payment amount")
                payments.append(
                    Payment(
                        amount=paid,
                        method=mydata.payment_method(row.get("method_code")),
                        method_code=mydata.normalize_code(row.get("method_code")),
                        method_label=commercial.get("PaymentMethodType") or None,
                        tip=self.num(row.get("tip"), "payment tip") or Decimal("0"),
                    )
                )
            return tuple(payments)
        return tuple(
            Payment(
                amount=self.required_num(row, "Amount", "payment amount"),
                method=vocabulary.payment_method(row.get("PaymentMethodType")),
                method_label=row.get("PaymentMethodType") or None,
            )
            for row in self.c.payments
        )

    def payload(self) -> dict:
        """Allowlisted, personal-data-free extraction kept with the receipt (D9).

        Only known fields are kept (requirements §15.3: an allowlist): an unknown field
        is reported by name in ``unknown_fields``, never stored with its value. The
        free-text miscellaneous section is not kept.
        """
        known = labels.COMMERCIAL_KNOWN

        def only(section: str, values: dict[str, str]) -> dict[str, str]:
            return {name: value for name, value in values.items() if name in known[section]}

        return {
            "commercial": {
                "issuer": only("header", self.c.issuer),
                "head_office": only("header", self.c.head_office),
                "branch": only("header", self.c.branch),
                "identity": only("identity", self.c.identity),
                "summary": only("summary", self.c.summary),
                "certification": only("certification", self.c.certification),
            },
            "tax": {
                "header": dict(self.t.header),
                "issuer": dict(self.t.issuer),
                "summary": dict(self.t.summary),
                "identifiers": {
                    key: value for key, value in self.t.identifiers.items() if key != "url"
                },
            },
        }


def _address(fields: Mapping[str, str]) -> Address | None:
    if not any(fields.values()):
        return None
    return Address(
        street=fields.get("Street") or None,
        number=fields.get("Number") or None,
        city=fields.get("City") or None,
        postal_code=fields.get("Postal") or None,
        country=fields.get("Country") or None,
    )
