"""AADE cash-register receipt check page → summary-only CanonicalReceipt.

The page shows AADE's record of a cash-register (ΦΗΜ) receipt: merchant, date and
time, totals, net/VAT per cash-register VAT category and the card amount. There
are no line items and no MARK (coverage says so). Alerts on the page (e.g. a QR
signature that differs from AADE's record) become notices, i.e. visible warnings.
"""

import re
from decimal import Decimal
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from apps.common.numbers import DateFormatError, parse_local_datetime
from apps.common.text import collapse_whitespace
from apps.receipts import vocabulary
from apps.receipts.canonical import (
    Address,
    Branch,
    CanonicalReceipt,
    Coverage,
    Document,
    Identity,
    Notice,
    Party,
    Payment,
    Totals,
    VatEntry,
)
from apps.receipts.errors import FormatChanged, InconsistentSource, ReceiptNotFound
from apps.receipts.links import parse_submitted_url
from apps.receipts.mydata import PaymentMethod
from apps.receipts.providers.aade_fhm.urls import PROVIDER_CODE, FhmLink, split
from apps.receipts.providers.base import UrlIdentity, parse_with_layouts
from apps.receipts.providers.html import amount, key_of, label_map, required, text_of

PARSER_VERSION = "aade_fhm/1"
CULTURE = "en"  # amounts use a decimal point: "€ 24.87"
SOURCE_TZ = ZoneInfo("Europe/Athens")
# Shown when AADE has no record (yet): e.g. fuel receipts are transmitted at day end.
NOT_TRANSMITTED = "δεν έχει διαβιβαστεί στην ΑΑΔΕ"
_TOTAL_LABEL = key_of("Συνολική αξία")

# Cash-register VAT categories → rate. Β and Γ are confirmed by the sample's
# arithmetic; Α, Δ, Ε follow the usual mapping and are checked per receipt (R14).
VAT_CATEGORIES = {
    "A": ("Α", Decimal("6")),
    "B": ("Β", Decimal("13")),
    "C": ("Γ", Decimal("24")),
    "D": ("Δ", Decimal("36")),
    "E": ("Ε", Decimal("0")),
}
FIELDS = {
    "Συνολική αξία": "gross",
    "Ποσό πληρωμής με κάρτα": "card",
    "Ημερομηνία, ώρα": "issued_at",
    "Ημερήσιος α/α": "daily_sequence",
    "ΦΗΜ": "register",
    "ΑΦΜ εκδότη": "vat",
    "Επωνυμία": "name",
    "Διεύθυνση": "address",
    "Αριθμός Ζ": "z_number",
    "Προοδευτικός α/α": "progressive",
    "Είδος παραστατικού": "type_label",
    "Σειρά": "series",
    "Αριθμός παραστατικού": "number",
    "Νόμισμα συναλλαγής": "currency",
    "Κωδικός καυσίμου (πρατήρια)": "fuel_code",
    "Λίτρα καυσίμου (πρατήρια)": "fuel_liters",
    "Αριθμός παροχής ρεύματος": "power_supply",
    **{f"Καθαρή αξία {letter}": f"net_{key}" for key, (letter, _rate) in VAT_CATEGORIES.items()},
    **{f"ΦΠΑ {letter}": f"vat_{key}" for key, (letter, _rate) in VAT_CATEGORIES.items()},
}
DROP = frozenset({key_of("ΑΦΜ λήπτη (σε τιμολόγιο)")})  # buyer VAT: personal
SIGNATURE_MISMATCH = "Διαφορά στην ψηφιακή υπογραφή"
# The page also echoes the receipt number and amount it read from the QR code (the URL).
_ECHO_SEQUENCE = re.compile(r"Με αύξοντα αριθμό \(α/α\)\s*(\d+)")
_ECHO_AMOUNT = re.compile(r"Συνολικού ποσού\s*([\d.,]+)\s*ευρώ")
_ADDRESS = re.compile(r"^(?P<street>.*?)\s*TK:\s*(?P<postal>\d{5})\s*(?P<city>.*)$")


class FhmLayoutV1:
    """Check page as observed 2026-11-14."""

    name = PARSER_VERSION

    def matches(self, soup: BeautifulSoup) -> bool:
        return any(key_of(text_of(td)) == _TOTAL_LABEL for td in soup.select("table.info td"))

    def parse(self, soup: BeautifulSoup, identity: UrlIdentity) -> CanonicalReceipt:
        return _build(soup, identity)


LAYOUTS = (FhmLayoutV1(),)


def parse_html(html: str, identity: UrlIdentity) -> CanonicalReceipt:
    soup = BeautifulSoup(html, "lxml")
    if NOT_TRANSMITTED in collapse_whitespace(soup.get_text(" ")):
        raise ReceiptNotFound("AADE has no record of this receipt (yet)")
    return parse_with_layouts(soup, identity, LAYOUTS)


def _num(text: str | None, where: str) -> Decimal | None:
    return amount(text, CULTURE, where)


def _build(soup: BeautifulSoup, identity: UrlIdentity) -> CanonicalReceipt:
    # The canonical URL was produced by recognize(), so it always splits.
    link: FhmLink = split(parse_submitted_url(identity.canonical_url))
    pairs = []
    for tr in soup.select("table.info tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) == 2 and key_of(text_of(cells[0])) not in DROP:
            pairs.append((text_of(cells[0]), text_of(cells[1])))
    values, unknown = label_map(pairs, FIELDS)

    register = required(values, "register", "cash register id")
    progressive = required(values, "progressive", "receipt sequence")
    if (
        register != link.register
        or not progressive.isdigit()
        or int(progressive) != int(link.sequence)
    ):
        raise InconsistentSource("the AADE record is for another receipt than the link")

    page_text = collapse_whitespace(soup.get_text(" "))
    echo = _ECHO_SEQUENCE.search(page_text)
    if echo and int(echo.group(1)) != int(link.sequence):
        raise InconsistentSource("the page echoes another receipt number than the link")

    gross = _num(required(values, "gross", "total"), "total")
    notices = []
    alerts = [text_of(alert) for alert in soup.select(".callout.alert")]
    if any(SIGNATURE_MISMATCH in alert for alert in alerts):
        notices.append(
            Notice(
                "signature_mismatch",
                "The QR signature differs from the data AADE holds for this receipt; "
                "AADE's data was used.",
            )
        )
    echo_amount = _ECHO_AMOUNT.search(page_text)
    if echo_amount and _num(echo_amount.group(1), "QR amount") != gross:
        notices.append(
            Notice("amount_mismatch", "The amount in the QR code differs from AADE's record.")
        )

    try:
        issued_at = parse_local_datetime(
            required(values, "issued_at", "date and time"),
            culture=CULTURE,
            order="ymd",
            tz=SOURCE_TZ,
        )
    except DateFormatError as exc:
        raise FormatChanged(str(exc)) from exc
    currency = vocabulary.currency(values.get("currency"))
    if currency is None:
        raise FormatChanged("missing or unknown currency")

    breakdown = []
    for key, (_letter, rate) in VAT_CATEGORIES.items():
        net = _num(values.get(f"net_{key}"), "net per category") or Decimal("0")
        vat = _num(values.get(f"vat_{key}"), "VAT per category") or Decimal("0")
        if net or vat:
            breakdown.append(
                VatEntry(
                    net=net,
                    vat=vat,
                    rate=rate,
                    category_code=vocabulary.vat_category_for_rate(rate),
                )
            )

    card = _num(values.get("card"), "card amount") or Decimal("0")
    payments = []
    if card > 0:
        payments.append(Payment(amount=card, method=PaymentMethod.CARD, method_label="ΚΑΡΤΑ"))
    if gross - card > 0:
        payments.append(Payment(amount=gross - card, method=PaymentMethod.CASH, derived=True))

    type_label = values.get("type_label") or None
    code, kind = vocabulary.document_type(type_label)
    series, number = values.get("series") or None, values.get("number") or None
    return CanonicalReceipt(
        provider_code=PROVIDER_CODE,
        parser_version=PARSER_VERSION,
        culture=CULTURE,
        source_url=identity.canonical_url,
        issuer=Party(
            country_code="GR",
            vat_number=required(values, "vat", "issuer VAT"),
            legal_name=required(values, "name", "merchant name"),
        ),
        branch=_branch(values.get("address")),
        document=Document(
            kind=kind,
            type_code=code,
            type_label=type_label,
            series=series,
            number=number,
            formatted_number=f"{series}-{number}" if series and number else number,
            issued_at=issued_at,
            issued_date=issued_at.date(),
            currency=currency,
        ),
        identity=Identity(source_key=link.source_key),
        totals=Totals(
            gross=gross,
            net=sum((entry.net for entry in breakdown), Decimal("0")),
            vat=sum((entry.vat for entry in breakdown), Decimal("0")),
        ),
        lines=(),
        vat_breakdown=tuple(breakdown),
        payments=tuple(payments),
        notices=tuple(notices),
        coverage=Coverage(
            line_items=False,
            line_tax_amounts=False,
            official_codes=False,
            mydata_registered=False,
            issue_time="exact",
            cross_checked=False,
        ),
        provider_payload={"record": values, "alerts": alerts},
        unknown_fields={f"record.{label}": value for label, value in unknown.items()},
    )


def _branch(address: str | None) -> Branch | None:
    if not address:
        return None
    match = _ADDRESS.match(address)
    if not match:
        return Branch(address=Address(street=address))
    return Branch(
        address=Address(
            street=match["street"] or None,
            postal_code=match["postal"],
            city=match["city"] or None,
        )
    )
