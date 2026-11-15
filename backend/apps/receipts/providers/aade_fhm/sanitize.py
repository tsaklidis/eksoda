"""Remove personal data from a saved AADE cash-register check page.

The page has little personal data: the buyer VAT (invoices only) is replaced in
place; the shop's register id and receipt numbers are business data and stay.
"""

from bs4 import BeautifulSoup

from apps.receipts.providers.aade_fhm.parser import DROP
from apps.receipts.providers.html import key_of, text_of
from apps.receipts.providers.sanitizing import (
    SanitizeResult,
    Secrets,
    finish,
    strip_active_content,
)


def sanitize_html(raw_html: str) -> SanitizeResult:
    soup = BeautifulSoup(raw_html, "lxml")
    secrets = Secrets()
    for tr in soup.select("table.info tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) == 2 and key_of(text_of(cells[0])) in DROP:
            secrets.replace_element(cells[1], "buyer")
    strip_active_content(soup)
    return finish(soup, secrets)
