"""Entersoft receipt URL recognition (docs/providers/entersoft.md §1)."""

import re
from dataclasses import dataclass

from apps.receipts.links import ParsedUrl
from apps.receipts.providers.base import UrlIdentity

PROVIDER_CODE = "entersoft"
HOST = "e-invoicing.gr"
DOCUMENT_PATH = "/api/GetInvoice"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# /edocuments/ViewInvoice/{ofenm}/{document UUID}_{access token}
_PATH_RE = re.compile(
    rf"^/edocuments/ViewInvoice/(-?\d{{1,6}})/({UUID})_([0-9a-z]{{4,32}})/?$", re.IGNORECASE
)


@dataclass(frozen=True)
class EntersoftLink:
    ofenm: str
    document_id: str  # lowercase UUID
    token: str  # access token, case preserved

    @property
    def canonical_url(self) -> str:
        return f"https://{HOST}/edocuments/ViewInvoice/{self.ofenm}/{self.document_id}_{self.token}"


def split(url: ParsedUrl) -> EntersoftLink | None:
    if url.host != HOST or url.query:
        return None
    match = _PATH_RE.match(url.path)
    if not match:
        return None
    ofenm, document_id, token = match.groups()
    return EntersoftLink(ofenm=ofenm, document_id=document_id.lower(), token=token)


def recognize(url: ParsedUrl) -> UrlIdentity | None:
    link = split(url)
    if link is None:
        return None
    return UrlIdentity(
        provider_code=PROVIDER_CODE,
        identity=f"entersoft:{link.document_id}",
        canonical_url=link.canonical_url,
    )
