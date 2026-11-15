"""SSRF-safe fetcher rules (requirements §15.1). No network: resolver and pool are fakes."""

import gzip
import io
import socket
from dataclasses import replace

import pytest
from urllib3.exceptions import (
    ConnectTimeoutError,
    NewConnectionError,
    ProtocolError,
    ReadTimeoutError,
    SSLError,
)
from urllib3.response import HTTPResponse

from apps.receipts.errors import (
    BlockedDestination,
    FormatChanged,
    ProviderHttpError,
    ProviderTimeout,
    ProviderUnreachable,
    ReceiptNotFound,
    ResponseTooLarge,
    UnexpectedContentType,
)
from apps.receipts.fetching import FetchLimits, SafeFetcher, https_pool, is_public_address
from apps.receipts.links import parse_submitted_url

HOST = "einvoice.impact.gr"
HOSTS = frozenset({HOST})
URL = parse_submitted_url(f"https://{HOST}/p/test?x=1")
PUBLIC_V4 = "93.184.216.34"
PUBLIC_V6 = "2606:2800:220:1:248:1893:25c8:1946"


class FakeResponse:
    def __init__(self, status=200, headers=None, chunks=(b"<html>ok</html>",)):
        self.status = status
        self.headers = {"Content-Type": "text/html; charset=utf-8", **(headers or {})}
        self.chunks = chunks
        self.closed = False

    def stream(self, amt, decode_content=True):
        yield from self.chunks

    def close(self):
        self.closed = True


class FakePool:
    def __init__(self, ip, host, response, error):
        self.ip, self.host = ip, host
        self.response, self.error = response, error
        self.calls = []
        self.closed = False

    def urlopen(self, method, target, **kwargs):
        self.calls.append((method, target, kwargs))
        if self.error is not None:
            raise self.error
        return self.response

    def close(self):
        self.closed = True


def make_fetcher(response=None, error=None, addresses=(PUBLIC_V4,), limits=None, clock=None):
    pools: list[FakePool] = []
    lookups: list[str] = []

    def resolver(host, port, type):
        lookups.append(host)
        return [
            (
                socket.AF_INET6 if ":" in ip else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (ip, port),
            )
            for ip in addresses
        ]

    def pool_factory(ip, host, fetch_limits):
        pool = FakePool(ip, host, response or FakeResponse(), error)
        pools.append(pool)
        return pool

    kwargs = {"resolver": resolver, "pool_factory": pool_factory}
    if clock is not None:
        kwargs["clock"] = clock
    return SafeFetcher(limits or FetchLimits(), **kwargs), pools, lookups


def test_successful_fetch_pins_the_validated_ip():
    fetcher, pools, _ = make_fetcher()
    document = fetcher.get(URL, allowed_hosts=HOSTS)

    assert document.body == b"<html>ok</html>"
    assert document.text() == "<html>ok</html>"
    assert (document.status, document.charset) == (200, "utf-8")
    pool = pools[0]
    assert (pool.ip, pool.host) == (PUBLIC_V4, HOST)  # connect to the IP, verify TLS for the host
    method, target, kwargs = pool.calls[0]
    assert (method, target) == ("GET", "/p/test?x=1")
    assert kwargs["redirect"] is False
    assert kwargs["retries"] is False
    assert set(kwargs["headers"]) == {
        "Host",
        "User-Agent",
        "Accept",
        "Accept-Language",
        "Accept-Encoding",
    }
    assert kwargs["headers"]["Host"] == HOST
    assert pool.closed
    assert pool.response.closed


def test_host_must_be_allowed_before_any_lookup():
    fetcher, _, lookups = make_fetcher()
    other = parse_submitted_url("https://example.com/p/test")
    with pytest.raises(BlockedDestination):
        fetcher.get(other, allowed_hosts=HOSTS)
    assert lookups == []


def test_only_port_443():
    fetcher, _, _ = make_fetcher()
    with pytest.raises(BlockedDestination):
        fetcher.get(replace(URL, port=8443), allowed_hosts=HOSTS)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.3.4",
        "192.168.1.10",
        "169.254.169.254",  # cloud metadata
        "100.64.0.1",  # carrier-grade NAT
        "0.0.0.0",  # noqa: S104
        "224.0.0.1",
        "240.0.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
        "2001:db8::1",
    ],
)
def test_non_public_addresses_are_blocked(address):
    fetcher, pools, _ = make_fetcher(addresses=(address,))
    with pytest.raises(BlockedDestination):
        fetcher.get(URL, allowed_hosts=HOSTS)
    assert pools == []


def test_any_non_public_answer_blocks_the_fetch():
    fetcher, _, _ = make_fetcher(addresses=(PUBLIC_V4, "10.0.0.1"))
    with pytest.raises(BlockedDestination):
        fetcher.get(URL, allowed_hosts=HOSTS)


def test_ipv4_is_preferred():
    fetcher, pools, _ = make_fetcher(addresses=(PUBLIC_V6, PUBLIC_V4))
    fetcher.get(URL, allowed_hosts=HOSTS)
    assert pools[0].ip == PUBLIC_V4


def test_dns_failures():
    def failing(*args, **kwargs):
        raise socket.gaierror("no such host")

    fetcher = SafeFetcher(resolver=failing)
    with pytest.raises(ProviderUnreachable, match="DNS"):
        fetcher.get(URL, allowed_hosts=HOSTS)
    empty, _, _ = make_fetcher(addresses=())
    with pytest.raises(ProviderUnreachable, match="no addresses"):
        empty.get(URL, allowed_hosts=HOSTS)


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (404, ReceiptNotFound),
        (408, ProviderHttpError),
        (429, ProviderHttpError),
        (503, ProviderHttpError),
        (301, FormatChanged),
        (302, FormatChanged),
        (403, FormatChanged),
    ],
)
def test_status_mapping(status, error):
    fetcher, _, _ = make_fetcher(response=FakeResponse(status=status))
    with pytest.raises(error):
        fetcher.get(URL, allowed_hosts=HOSTS)


@pytest.mark.parametrize("content_type", ["application/json", ""])
def test_only_html_is_accepted(content_type):
    fetcher, _, _ = make_fetcher(response=FakeResponse(headers={"Content-Type": content_type}))
    with pytest.raises(UnexpectedContentType):
        fetcher.get(URL, allowed_hosts=HOSTS)


def test_declared_length_over_the_limit():
    response = FakeResponse(headers={"Content-Length": str(10_000)})
    fetcher, _, _ = make_fetcher(response=response, limits=FetchLimits(max_bytes=1000))
    with pytest.raises(ResponseTooLarge):
        fetcher.get(URL, allowed_hosts=HOSTS)


def test_streamed_body_over_the_limit():
    response = FakeResponse(chunks=(b"x" * 6, b"x" * 6))
    fetcher, _, _ = make_fetcher(response=response, limits=FetchLimits(max_bytes=10))
    with pytest.raises(ResponseTooLarge):
        fetcher.get(URL, allowed_hosts=HOSTS)


def _gzip_response(payload: bytes) -> HTTPResponse:
    return HTTPResponse(
        body=io.BytesIO(gzip.compress(payload)),
        headers={"Content-Type": "text/html", "Content-Encoding": "gzip"},
        status=200,
        preload_content=False,
        decode_content=True,
    )


def test_gzip_bodies_are_decoded():
    fetcher, _, _ = make_fetcher(response=_gzip_response("<html>Γάλα</html>".encode()))
    assert fetcher.get(URL, allowed_hosts=HOSTS).text() == "<html>Γάλα</html>"


def test_decompression_bomb_is_capped_after_decoding():
    bomb = _gzip_response(b"0" * 5_000_000)  # ~5 KB compressed, 5 MB decoded
    fetcher, _, _ = make_fetcher(response=bomb, limits=FetchLimits(max_bytes=2_000_000))
    with pytest.raises(ResponseTooLarge):
        fetcher.get(URL, allowed_hosts=HOSTS)


def test_overall_deadline():
    ticks = iter([0.0, 31.0])
    response = FakeResponse(chunks=(b"a", b"b"))
    fetcher, _, _ = make_fetcher(response=response, clock=lambda: next(ticks))
    with pytest.raises(ProviderTimeout, match="deadline"):
        fetcher.get(URL, allowed_hosts=HOSTS)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (NewConnectionError(None, "refused"), ProviderUnreachable),
        (SSLError("bad certificate"), ProviderUnreachable),
        (ConnectTimeoutError("slow"), ProviderTimeout),
        (ReadTimeoutError(None, "/p/test", "slow"), ProviderTimeout),
        (TimeoutError("slow"), ProviderTimeout),
        (ProtocolError("reset"), ProviderUnreachable),
        (OSError("broken"), ProviderUnreachable),
    ],
)
def test_transport_errors_are_mapped(error, expected):
    fetcher, pools, _ = make_fetcher(error=error)
    with pytest.raises(expected):
        fetcher.get(URL, allowed_hosts=HOSTS)
    assert pools[0].closed


def test_charset_defaults_to_utf8():
    response = FakeResponse(headers={"Content-Type": 'text/html; charset="ISO-8859-7"'})
    fetcher, _, _ = make_fetcher(response=response)
    assert fetcher.get(URL, allowed_hosts=HOSTS).charset == "iso-8859-7"
    plain = FakeResponse(headers={"Content-Type": "text/html"})
    fetcher, _, _ = make_fetcher(response=plain)
    assert fetcher.get(URL, allowed_hosts=HOSTS).charset == "utf-8"


def test_is_public_address():
    assert is_public_address(PUBLIC_V4)
    assert is_public_address(PUBLIC_V6)
    assert not is_public_address("not-an-ip")
    assert not is_public_address("::ffff:10.0.0.1")


def test_https_pool_verifies_the_hostname_while_connecting_to_the_ip():
    pool = https_pool(PUBLIC_V4, HOST, FetchLimits(connect_timeout=1, read_timeout=2))
    try:
        assert pool.host == PUBLIC_V4
        assert pool.assert_hostname == HOST
        assert pool.conn_kw["server_hostname"] == HOST
        assert pool.cert_reqs == "CERT_REQUIRED"
        assert pool.retries is False
    finally:
        pool.close()


def test_accepted_statuses_are_returned_for_the_provider():
    response = FakeResponse(status=418, chunks=(b"<html>Error 404: Page not found.</html>",))
    fetcher, _, _ = make_fetcher(response=response)
    document = fetcher.get(URL, allowed_hosts=HOSTS, accept_statuses=frozenset({418}))
    assert document.status == 418
    with pytest.raises(FormatChanged):
        make_fetcher(response=FakeResponse(status=418))[0].get(URL, allowed_hosts=HOSTS)


def test_unknown_charset_is_a_format_change():
    from apps.receipts.fetching import FetchedDocument

    document = FetchedDocument(b"<html></html>", charset="utf8mb4")
    with pytest.raises(FormatChanged, match="charset"):
        document.text()
