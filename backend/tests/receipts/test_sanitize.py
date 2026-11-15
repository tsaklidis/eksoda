import pytest

from apps.receipts.providers.impact import labels
from apps.receipts.providers.impact.sanitize import FAKE_GUID, sanitize_html
from apps.receipts.providers.sanitizing import SanitizeError, Secrets, fake_like, verify
from tests.receipts import impact

REAL_GUID = "0123456789ABCDEF0123456789ABCDEF"


def raw_like_page() -> str:
    """The sanitized sample with personal values put back (as on a real page)."""
    soup = impact.page()
    for value in soup.select(".CounterParty .value"):
        if not value.select(".value"):
            value.string = "BUYER-NAME-1234"
    impact.set_field(soup, "TransactionId", "555000111222333444555")
    impact.set_field(soup, "Authentication", "ABCDEF0123456789ABCDEF0123456789ABCDEF01")
    for label in labels.TAX_DROP:
        for cell in impact.tax_cells(soup, label):
            cell.string = "MEUCIA+P6NdJsT4Qs=SECRET"
    html = str(soup).replace("0" * 32, REAL_GUID)
    html = html.replace('class="qrcode-container"', 'class="qrcode-container"><svg>QR</svg')
    return html.replace(
        "</body>",
        '<a href="https://mydatapi.aade.gr/myDATA/TimologioQR/QRInfo?q=abc%2fdef">myDATA</a>'
        '<input type="hidden" name="__RequestVerificationToken" value="tok-123"></body>',
    )


def test_sanitize_removes_personal_values():
    raw = raw_like_page()
    for secret in ("BUYER-NAME-1234", "555000111222333444555", "MEUCIA", REAL_GUID):
        assert secret in raw
    result = sanitize_html(raw)
    for secret in (
        "BUYER-NAME-1234",
        "555000111222333444555",
        "MEUCIA",
        REAL_GUID,
        "q=abc",
        "tok-123",
    ):
        assert secret not in result.html
    assert FAKE_GUID in result.html
    assert "<svg>QR</svg>" not in result.html
    assert result.replaced["url_access_guid"] >= 1
    assert result.replaced["counterparty"] == 1
    assert result.replaced["payment_or_signature"] == 3

    # The sanitized page still parses to the same receipt as the fixture.
    assert impact.parse(result.html).totals == impact.parse(impact.read()).totals


def test_sanitizing_is_idempotent_on_fixtures():
    fixture = impact.read()
    again = sanitize_html(fixture).html
    assert impact.parse(again).to_json() == impact.parse(fixture).to_json()


def test_not_found_page_guid_is_replaced():
    raw = impact.read("not_found.html").replace("0" * 32, REAL_GUID)
    assert REAL_GUID not in sanitize_html(raw).html


def test_verification_refuses_leaks():
    secrets = Secrets()
    secrets.record("SECRET-VALUE", "counterparty")
    with pytest.raises(SanitizeError, match="counterparty"):
        verify("<p>still here: SECRET-VALUE</p>", secrets)


def test_short_values_are_replaced_structurally_and_fakes_are_skipped():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(
        "<p><b>ΝΙΚ</b><i>0000000000</i><u>XXXX XX</u><s>ΝΙΚΑΣ ΣΑΛΑΜΙ</s></p>", "lxml"
    )
    secrets = Secrets()
    for tag in ("b", "i", "u"):
        secrets.replace_element(soup.find(tag), "customer")
    assert soup.find("b").string == "XXX"  # short values are not skipped any more
    assert soup.find("s").string == "ΝΙΚΑΣ ΣΑΛΑΜΙ"  # unrelated text is never touched
    assert dict(secrets.items()) == {"ΝΙΚ": "customer"}  # fakes are not secrets


def test_patterns_replace_only_link_occurrences():
    import re

    token = "7abc1234"
    html = f'<a href="https://x.gr/v/{token}">x</a><td>item code {token}</td>'
    secrets = Secrets()
    secrets.replace_pattern(re.compile(r"/v/([0-9a-z]+)"), lambda t: "0xxx0000", "token")
    output = secrets._apply_patterns(html)
    assert "/v/0xxx0000" in output
    assert f"item code {token}" in output  # the same text outside a link is left alone
    assert dict(secrets.items()) == {token: "token"}
    # Verification then refuses the page, instead of silently corrupting the item code.
    with pytest.raises(SanitizeError, match="token"):
        verify(output, secrets)


def test_fake_like_keeps_the_shape():
    assert fake_like("AB12+/=") == "XX00+/="
