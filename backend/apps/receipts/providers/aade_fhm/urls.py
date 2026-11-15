"""AADE cash-register (ΦΗΜ) receipt check URL recognition (docs/providers/aade.md §1)."""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs

from apps.receipts.links import ParsedUrl
from apps.receipts.providers.base import UrlIdentity

PROVIDER_CODE = "aade_fhm"
HOST = "www1.aade.gr"
PATH = "/tameiakes/myweb/q1.php"
# SIG = register id (3 letters + 8 digits) + receipt sequence (8 digits) + signature,
# date and amount. Only the first two parts are needed: the page repeats the rest.
_SIG_RE = re.compile(
    r"^(?P<register>[A-Z]{3}\d{8})(?P<sequence>\d{8})(?P<rest>[0-9A-Z]{10,}\.\d{2})$"
)


@dataclass(frozen=True)
class FhmLink:
    sig: str
    register: str
    sequence: str

    @property
    def canonical_url(self) -> str:
        return f"https://{HOST}{PATH}?SIG={self.sig}"

    @property
    def source_key(self) -> str:
        return f"fhm:{self.register}:{self.sequence}"


def split(url: ParsedUrl) -> FhmLink | None:
    if url.host != HOST or url.path != PATH:
        return None
    params = parse_qs(url.query, keep_blank_values=True)
    if set(params) != {"SIG"} or len(params["SIG"]) != 1:
        return None
    sig = params["SIG"][0].strip()
    match = _SIG_RE.match(sig)
    if not match:
        return None
    return FhmLink(sig=sig, register=match["register"], sequence=match["sequence"])


def recognize(url: ParsedUrl) -> UrlIdentity | None:
    link = split(url)
    if link is None:
        return None
    return UrlIdentity(
        provider_code=PROVIDER_CODE, identity=link.source_key, canonical_url=link.canonical_url
    )
