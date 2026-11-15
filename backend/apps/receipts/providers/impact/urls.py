"""Impact receipt URL recognition (docs/providers/impact.md §1)."""

import re

from apps.receipts.links import ParsedUrl
from apps.receipts.providers.base import UrlIdentity

PROVIDER_CODE = "impact"
HOST = "einvoice.impact.gr"
# /p/{country prefix + 9-digit VAT}/{40-hex UID}/{32-hex access GUID}
_PATH_RE = re.compile(r"^/p/([A-Z]{2})(\d{9})/([0-9A-F]{40})/([0-9A-F]{32})/?$", re.IGNORECASE)
# VAT prefixes (EU VIES style) → ISO country codes.
COUNTRY_BY_PREFIX = {"EL": "GR"}


def recognize(url: ParsedUrl) -> UrlIdentity | None:
    if url.host != HOST or url.query:
        return None
    match = _PATH_RE.match(url.path)
    if not match:
        return None
    prefix, vat, uid, guid = match.groups()
    prefix, uid, guid = prefix.upper(), uid.upper(), guid.upper()
    country = COUNTRY_BY_PREFIX.get(prefix)
    if country is None:
        return None
    return UrlIdentity(
        provider_code=PROVIDER_CODE,
        identity=f"{country}:{vat}:{uid}",
        canonical_url=f"https://{HOST}/p/{prefix}{vat}/{uid}/{guid}",
        issuer_country=country,
        issuer_vat=vat,
        uid=uid,
    )
