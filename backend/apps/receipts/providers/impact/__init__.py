"""Impact SA e-receipt provider (einvoice.impact.gr). Format: docs/providers/impact.md."""

from apps.receipts.providers.base import Provider
from apps.receipts.providers.impact.parser import LAYOUTS, parse_html
from apps.receipts.providers.impact.sanitize import sanitize_html
from apps.receipts.providers.impact.urls import HOST, PROVIDER_CODE, recognize

provider = Provider(
    code=PROVIDER_CODE,
    hosts=frozenset({HOST}),
    layouts=LAYOUTS,
    recognize=recognize,
    parse_html=parse_html,
    sanitize=sanitize_html,
)
