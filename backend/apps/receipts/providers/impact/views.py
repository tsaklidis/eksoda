"""Extraction of the two views of an Impact receipt page into plain string maps.

Nothing here interprets values: numbers, dates and codes stay strings. Personal
fields (counterparty, payment transaction ids, signatures) are never read.
"""

from dataclasses import dataclass, field

from bs4 import Tag

from apps.receipts.providers.html import text_of
from apps.receipts.providers.impact import labels

StrMap = dict[str, str]


def field_name(element: Tag) -> str | None:
    for css_class in element.get("class") or []:
        if css_class.startswith("field-"):
            return css_class[len("field-") :]
    return None


# --- Commercial view --------------------------------------------------------------
@dataclass
class CommercialView:
    issuer: StrMap = field(default_factory=dict)
    head_office: StrMap = field(default_factory=dict)
    branch: StrMap = field(default_factory=dict)
    identity: StrMap = field(default_factory=dict)
    lines: list[StrMap] = field(default_factory=list)
    vat_breakdown: list[StrMap] = field(default_factory=list)
    payments: list[StrMap] = field(default_factory=list)
    summary: StrMap = field(default_factory=dict)
    certification: StrMap = field(default_factory=dict)
    unknown: StrMap = field(default_factory=dict)


def _note_unknown(view: CommercialView, section: str, name: str, value: str) -> None:
    if name not in labels.COMMERCIAL_KNOWN[section]:
        view.unknown[f"commercial.{section}.{name}"] = value


def _fields(container: Tag | None, selector: str = ".field"):
    """(name, value) for every field element under ``container`` with a .value child."""
    if container is None:
        return
    for element in container.select(selector):
        name = field_name(element)
        value_element = element.select_one(".value")
        if name is None or value_element is None or name in labels.COMMERCIAL_DROP:
            continue
        yield name, text_of(value_element)


def _rows(container: Tag | None) -> list[StrMap]:
    rows: list[StrMap] = []
    if container is None:
        return rows
    for tr in container.select("tbody tr"):
        row = {}
        for td in tr.find_all("td"):
            name = field_name(td)
            if name and name not in labels.COMMERCIAL_DROP:
                row[name] = text_of(td.select_one(".value") or td)
        if row:
            rows.append(row)
    return rows


def extract_commercial(invoice: Tag) -> CommercialView:
    view = CommercialView()

    # Header: issuer fields, then up to two address blocks (head office, branch).
    address_blocks: list[StrMap] = [{}]
    for name, value in _fields(invoice.select_one(".section-header")):
        if name in labels.ADDRESS_FIELDS:
            if name in address_blocks[-1]:
                address_blocks.append({})
            address_blocks[-1][name] = value
        else:
            view.issuer.setdefault(name, value)
        _note_unknown(view, "header", name, value)
    view.head_office = address_blocks[0]
    view.branch = address_blocks[1] if len(address_blocks) > 1 else {}
    if len(address_blocks) > 2:
        view.unknown["commercial.header.extra_address_blocks"] = str(len(address_blocks) - 2)

    for name, value in _fields(invoice.select_one(".section-identity")):
        view.identity[name] = value
        _note_unknown(view, "identity", name, value)

    view.lines = _rows(invoice.select_one(".section-details"))
    for row in view.lines:
        for name, value in row.items():
            _note_unknown(view, "line", name, value)

    view.vat_breakdown = _rows(invoice.select_one(".section-taxes"))

    # Payment rows are <tr class="field field-X"><td class="value">; a method row
    # starts a new payment.
    for name, value in _fields(invoice.select_one(".section-paymentanalysis"), "tr.field"):
        if name == "PaymentMethodType" or not view.payments:
            view.payments.append({})
        view.payments[-1][name] = value
        _note_unknown(view, "payment", name, value)

    for name, value in _fields(invoice.select_one(".section-summaries"), "tr.field"):
        view.summary[name] = value
        _note_unknown(view, "summary", name, value)

    for name, value in _fields(invoice.select_one(".section-certification")):
        view.certification.setdefault(name, value)
        _note_unknown(view, "certification", name, value)

    return view


# --- Tax view (myDATA) ---------------------------------------------------------------
@dataclass
class TaxView:
    header: StrMap = field(default_factory=dict)
    issuer: StrMap = field(default_factory=dict)
    summary: StrMap = field(default_factory=dict)
    payments: list[StrMap] = field(default_factory=list)
    identifiers: StrMap = field(default_factory=dict)
    lines: list[StrMap] = field(default_factory=list)
    unknown: StrMap = field(default_factory=dict)


_SECTION_LABELS = {
    "header": labels.TAX_HEADER,
    "issuer": labels.TAX_ISSUER,
    "summary": labels.TAX_SUMMARY,
    "payment": labels.TAX_PAYMENT,
    "identifiers": labels.TAX_IDENTIFIERS,
    "line": labels.TAX_LINE,
}


def _section_of(tr: Tag) -> tuple[str, Tag]:
    """The tax-view section of a label/value row and the element that groups it.

    Rows of one line or one payment share a group element; extract_tax_view() turns each
    group into one row map.
    """
    table = tr.find_parent("table")
    classes = set(table.get("class") or [])
    line_div = tr.find_parent("div", class_="InvoiceLines")
    if line_div is not None:
        return "line", line_div
    if "InvoiceSummary" in classes:
        return "summary", table
    if "PaymentMethodType" in classes:
        return "payment", table
    if "Party" in classes:
        title = text_of(table.find("h3"))
        return ("issuer" if title == labels.ISSUER_PARTY_TITLE else "counterparty"), table
    if tr.find_parent("div", class_="InvoiceHeader") is not None:
        return "header", table
    return "identifiers", table


def _key_for(section: str, label: str) -> str | None:
    key = _SECTION_LABELS[section].get(label)
    if key is None and section == "identifiers":
        for prefix, prefixed_key in labels.TAX_IDENTIFIER_PREFIXES.items():
            if label.startswith(prefix):
                return prefixed_key
    return key


def extract_tax_view(container: Tag) -> TaxView:
    view = TaxView()
    # id(group element) → (section, row map), in document order
    groups: dict[int, tuple[str, StrMap]] = {}
    for tr in container.find_all("tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) != 2:
            continue
        label, value = text_of(cells[0]), text_of(cells[1])
        if not label or label in labels.TAX_DROP:
            continue
        section, group = _section_of(tr)
        if section == "counterparty":
            continue  # buyer data is personal: never read
        key = _key_for(section, label)
        if key is None:
            # Payment values may be personal; keep only that the label appeared.
            view.unknown[f"tax.{section}.{label}"] = "" if section == "payment" else value
            continue
        groups.setdefault(id(group), (section, {}))[1][key] = value

    for section, values in groups.values():
        if section == "line":
            view.lines.append(values)
        elif section == "payment":
            view.payments.append(values)
        else:
            getattr(view, section).update(values)
    return view
