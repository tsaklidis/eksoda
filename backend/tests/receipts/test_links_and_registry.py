from dataclasses import replace

import pytest

from apps.receipts.errors import InvalidUrl, UnsupportedProvider, UnsupportedUrlFormat
from apps.receipts.links import ParsedUrl, parse_submitted_url
from apps.receipts.providers import ProviderRegistry, impact, registry
from apps.receipts.providers.base import mask_url

UID = "FA8355776160C1AF53AC6A860C29C0BB1437029F"
GUID = "0123456789ABCDEF0123456789ABCDEF"
VALID = f"https://einvoice.impact.gr/p/EL094062259/{UID}/{GUID}"


def test_parse_valid_url():
    url = parse_submitted_url("  HTTPS://EInvoice.Impact.gr:443/p/x?a=1  ")
    assert url == ParsedUrl("https", "einvoice.impact.gr", 443, "/p/x", "a=1")
    assert url.target == "/p/x?a=1"
    assert url.geturl() == "https://einvoice.impact.gr:443/p/x?a=1"
    assert parse_submitted_url("https://example.com").path == "/"


def test_idna_hosts_are_encoded():
    assert parse_submitted_url("https://παράδειγμα.gr/p").host == "xn--hxajbheg2az3al.gr"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "http://einvoice.impact.gr/p/x",
        "ftp://einvoice.impact.gr/p/x",
        "https://user:pass@einvoice.impact.gr/p/x",
        "https://einvoice.impact.gr/p/x#frag",
        "https://einvoice.impact.gr:8443/p/x",
        "https://einvoice.impact.gr:99999/p/x",
        "https:///p/x",
        "https://einvoice.impact.gr/p/a b",
        "https://einvoice.impact.gr/p/\x00",
        "https://" + "a" * 2050 + ".gr",
        "https://xn--/p",
    ],
)
def test_invalid_urls(raw):
    with pytest.raises(InvalidUrl):
        parse_submitted_url(raw)


def test_impact_recognition_canonicalizes():
    provider, identity = registry.resolve_url(VALID.lower().replace("/p/el", "/p/EL") + "/")
    assert provider.code == "impact"
    assert identity.canonical_url == VALID
    assert identity.identity == f"GR:094062259:{UID}"
    assert (identity.issuer_country, identity.issuer_vat, identity.uid) == ("GR", "094062259", UID)
    assert len(identity.url_fingerprint) == 64
    assert mask_url(identity.canonical_url).endswith("/********")
    assert GUID not in mask_url(identity.canonical_url)


@pytest.mark.parametrize(
    "path",
    [
        f"/p/EL094062259/{UID}",
        f"/p/EL09406225/{UID}/{GUID}",
        f"/p/CY094062259/{UID}/{GUID}",
        f"/p/EL094062259/{UID[:-1]}/{GUID}",
        f"/x/EL094062259/{UID}/{GUID}",
        f"/p/EL094062259/{UID}/{GUID}?lang=en",
    ],
)
def test_unknown_impact_paths(path):
    with pytest.raises(UnsupportedUrlFormat):
        registry.resolve_url(f"https://einvoice.impact.gr{path}")


def test_unknown_hosts():
    with pytest.raises(UnsupportedProvider):
        registry.resolve_url("https://einvoice.example.gr/p/x")


def test_registry_rules():
    assert registry.codes == ["aade_fhm", "entersoft", "impact"]
    with pytest.raises(ValueError, match="already registered"):
        ProviderRegistry([impact.provider, impact.provider])
    with pytest.raises(ValueError, match="host"):
        ProviderRegistry([impact.provider, replace(impact.provider, code="other")])
    with pytest.raises(UnsupportedProvider):
        ProviderRegistry().get("impact")


def test_mask_url_keeps_short_urls():
    assert mask_url("https://example.com/a") == "https://example.com/a"
