"""Provider contract and shared building blocks (pure Python, requirements §7).

A provider recognizes its URLs, fetches its pages through the SafeFetcher, parses
them with one of its *layouts*, and sanitizes saved pages for test fixtures.
Layouts make format changes cheap: when a provider changes its page, add a new
layout next to the old one (old fixtures keep passing) and register it first.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from bs4 import BeautifulSoup

from apps.common.text import fingerprint
from apps.receipts.canonical import CanonicalReceipt
from apps.receipts.errors import FormatChanged
from apps.receipts.fetching import FetchedDocument, SafeFetcher
from apps.receipts.links import ParsedUrl, parse_submitted_url
from apps.receipts.providers.sanitizing import SanitizeResult


@dataclass(frozen=True)
class UrlIdentity:
    """What a provider learns from a URL before fetching (pre-fetch dedup, §6.3)."""

    provider_code: str
    identity: str  # e.g. "GR:094062259:<UID>", "entersoft:<uuid>", "fhm:<register>:<seq>"
    canonical_url: str
    issuer_country: str | None = None  # known pre-fetch only for some providers
    issuer_vat: str | None = None
    uid: str | None = None

    @property
    def url_fingerprint(self) -> str:
        return fingerprint(self.canonical_url)


def mask_url(url: str) -> str:
    """Hide the secret part of a receipt URL: the query, else the last path segment."""
    base, separator, query = url.partition("?")
    if separator and query:
        return f"{base}?{'*' * 8}"
    head, _, last = url.rstrip("/").rpartition("/")
    return f"{head}/{'*' * 8}" if head and len(last) >= 16 else url


class Layout(Protocol):
    """One known page format of a provider."""

    name: str  # also the parser version stored with each receipt, e.g. "impact/1"

    def matches(self, soup: BeautifulSoup) -> bool: ...

    def parse(self, soup: BeautifulSoup, identity: UrlIdentity) -> CanonicalReceipt: ...


def parse_with_layouts(
    soup: BeautifulSoup, identity: UrlIdentity, layouts: Sequence[Layout]
) -> CanonicalReceipt:
    for layout in layouts:
        if layout.matches(soup):
            return layout.parse(soup, identity)
    raise FormatChanged("no known layout matches the page")


@dataclass
class Provider:
    """A receipt source: its hosts plus the functions of its urls/parser/sanitize modules."""

    code: str
    hosts: frozenset[str]
    layouts: Sequence[Layout]  # newest first
    recognize: Callable[[ParsedUrl], UrlIdentity | None]
    parse_html: Callable[[str, UrlIdentity], CanonicalReceipt]
    sanitize: Callable[[str], SanitizeResult]
    # Only for sources that need more than one GET of the canonical URL (Entersoft).
    fetch_document: Callable[[UrlIdentity, SafeFetcher], FetchedDocument] | None = None

    def fetch(self, identity: UrlIdentity, fetcher: SafeFetcher) -> FetchedDocument:
        if self.fetch_document is not None:
            return self.fetch_document(identity, fetcher)
        return fetcher.get(parse_submitted_url(identity.canonical_url), allowed_hosts=self.hosts)

    def parse(self, doc: FetchedDocument, identity: UrlIdentity) -> CanonicalReceipt:
        return self.parse_html(doc.text(), identity)
