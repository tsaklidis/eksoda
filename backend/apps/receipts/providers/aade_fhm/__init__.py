"""AADE cash-register (ΦΗΜ) receipt check page (www1.aade.gr). Format: docs/providers/aade.md."""

from apps.receipts.providers.aade_fhm import urls
from apps.receipts.providers.aade_fhm.parser import LAYOUTS, parse_html
from apps.receipts.providers.aade_fhm.sanitize import sanitize_html
from apps.receipts.providers.base import Provider

provider = Provider(
    code=urls.PROVIDER_CODE,
    hosts=frozenset({urls.HOST}),
    layouts=LAYOUTS,
    recognize=urls.recognize,
    parse_html=parse_html,
    sanitize=sanitize_html,
)
