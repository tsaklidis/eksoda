"""Remove personal data from saved Entersoft pages (shell or receipt document).

Replaced in place: document UUIDs and access tokens inside receipt links and frame
parameters, customer block values, the provider AuthenticationCode, download
tokens. Removed: scripts/styles, the QR image URL (it encodes the receipt link),
the myDATA QR token.
"""

import re

from bs4 import BeautifulSoup

from apps.receipts.providers.entersoft.parser import CUSTOMER_BLOCK, REMARK_DROP
from apps.receipts.providers.entersoft.urls import UUID
from apps.receipts.providers.html import child_cells, key_of, text_of
from apps.receipts.providers.sanitizing import (
    SanitizeResult,
    Secrets,
    fake_like,
    finish,
    strip_active_content,
)

FAKE_UUID = "00000000-0000-4000-8000-000000000000"
_LINK_ID = re.compile(rf"({UUID})_[0-9a-z]{{4,32}}", re.IGNORECASE)
_LINK_TOKEN = re.compile(rf"{UUID}_([0-9a-z]{{4,32}})", re.IGNORECASE)
_PARAM_ID = re.compile(r"intRefDocID=([0-9a-z-]+)", re.IGNORECASE)
_PARAM_TOKEN = re.compile(r"hashToken=([0-9a-z]+)", re.IGNORECASE)


def _fake_token(token: str) -> str:
    return fake_like(token, letter="x")


def sanitize_html(raw_html: str) -> SanitizeResult:
    soup = BeautifulSoup(raw_html, "lxml")
    secrets = Secrets()

    for block in soup.select(".backgrey"):
        title = block.select_one(".BoldBlueHeader")
        if title is not None and key_of(text_of(title)) == CUSTOMER_BLOCK:
            for row in block.select("div.row"):
                cells = child_cells(row)
                if len(cells) == 2:
                    secrets.replace_element(cells[1], "customer")
    for row in soup.select("div.row"):
        cells = child_cells(row)
        if len(cells) == 2 and key_of(text_of(cells[0])) in REMARK_DROP:
            secrets.replace_element(cells[1], "signature")

    for element in soup.select("[data-download-token]"):
        secrets.replace_attribute(element, "data-download-token", "download_token")
    for image in soup.select('img[src*="CreateBarcode"]'):
        image["src"] = "/api/CreateBarcode?barcode=REDACTED"
    for anchor in soup.select('a[href*="mydatapi.aade.gr"]'):
        anchor["href"] = "https://mydatapi.aade.gr/myDATA/TimologioQR/QRInfo?q=REDACTED"
    strip_active_content(soup)

    secrets.replace_pattern(_LINK_ID, lambda _id: FAKE_UUID, "url_access_token")
    secrets.replace_pattern(_LINK_TOKEN, _fake_token, "url_access_token")
    secrets.replace_pattern(_PARAM_ID, lambda _id: FAKE_UUID, "url_access_token")
    secrets.replace_pattern(_PARAM_TOKEN, _fake_token, "url_access_token")
    return finish(soup, secrets)
