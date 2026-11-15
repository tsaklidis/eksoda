"""Entersoft e-receipt provider (e-invoicing.gr). Format: docs/providers/entersoft.md."""

from apps.receipts.errors import FormatChanged, ReceiptNotFound
from apps.receipts.fetching import FetchedDocument, SafeFetcher
from apps.receipts.links import parse_submitted_url
from apps.receipts.providers.base import Provider, UrlIdentity
from apps.receipts.providers.entersoft import urls
from apps.receipts.providers.entersoft.parser import (
    LAYOUTS,
    document_url_from_shell,
    is_not_found,
    parse_html,
)
from apps.receipts.providers.entersoft.sanitize import sanitize_html

HOSTS = frozenset({urls.HOST})
# The document endpoint answers 418 (with an "Error 404" page) for unknown documents.
_NOT_FOUND_STATUSES = frozenset({418})


def fetch_document(identity: UrlIdentity, fetcher: SafeFetcher) -> FetchedDocument:
    """Two requests on the same host: the shell page, then the document it frames."""
    page_url = parse_submitted_url(identity.canonical_url)
    shell = fetcher.get(page_url, allowed_hosts=HOSTS)
    document_url = document_url_from_shell(shell.text(), urls.split(page_url))
    document = fetcher.get(document_url, allowed_hosts=HOSTS, accept_statuses=_NOT_FOUND_STATUSES)
    if document.status != 200:
        if is_not_found(document.text()):
            raise ReceiptNotFound(f"HTTP {document.status} with a not-found page")
        raise FormatChanged(f"unexpected HTTP status {document.status}")
    return document


provider = Provider(
    code=urls.PROVIDER_CODE,
    hosts=HOSTS,
    layouts=LAYOUTS,
    recognize=urls.recognize,
    parse_html=parse_html,
    sanitize=sanitize_html,
    fetch_document=fetch_document,
)
