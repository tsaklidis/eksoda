"""Remove personal data from a saved Impact receipt page so it can be a test fixture.

Replaced in place (shape-preserving fakes): buyer/counterparty values, payment
transaction ids, POS terminal id, payment and provider signatures, and the URL
access GUID (→ 32 zeros) wherever a receipt link or the not-found message shows it.
Removed: scripts, styles, the QR code (it encodes the URL) and the myDATA QR token.
The result is verified by the shared ``finish``.
"""

import re

from bs4 import BeautifulSoup

from apps.receipts.providers.html import text_of
from apps.receipts.providers.impact import labels
from apps.receipts.providers.impact.views import field_name
from apps.receipts.providers.sanitizing import (
    SanitizeResult,
    Secrets,
    finish,
    strip_active_content,
)

FAKE_GUID = "0" * 32
_GUID_PATTERNS = (
    re.compile(r"/p/[A-Z]{2}\d{9}/[0-9A-F]{40}/([0-9A-F]{32})", re.IGNORECASE),  # receipt links
    re.compile(r"Guid\s+([0-9A-F]{32})", re.IGNORECASE),  # the not-found message
)


def sanitize_html(raw_html: str) -> SanitizeResult:
    soup = BeautifulSoup(raw_html, "lxml")
    secrets = Secrets()

    for value_element in soup.select(".CounterParty .value"):
        if not value_element.select(".value"):  # leaf values only
            secrets.replace_element(value_element, "counterparty")
    for element in soup.select(".field"):
        if field_name(element) in labels.COMMERCIAL_DROP:
            secrets.replace_element(element.select_one(".value"), "payment_or_signature")

    for tr in soup.select(".InvoicesDocDetailed tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) != 2:
            continue
        label = text_of(cells[0])
        table = tr.find_parent("table")
        # Party tables are told apart only by their <h3> title; any party that is not the
        # issuer is the buyer.
        in_counterparty = "Party" in (table.get("class") or []) and (
            text_of(table.find("h3")) != labels.ISSUER_PARTY_TITLE
        )
        if label in labels.TAX_DROP:
            secrets.replace_element(cells[1], "payment_or_signature")
        elif in_counterparty:
            secrets.replace_element(cells[1], "counterparty")

    strip_active_content(soup)
    for container in soup.select(".qrcode-container"):
        container.clear()
    for anchor in soup.select('a[href*="mydatapi.aade.gr"]'):
        anchor["href"] = "https://mydatapi.aade.gr/myDATA/TimologioQR/QRInfo?q=REDACTED"
    for pattern in _GUID_PATTERNS:
        secrets.replace_pattern(pattern, lambda _guid: FAKE_GUID, "url_access_guid")
    return finish(soup, secrets)
