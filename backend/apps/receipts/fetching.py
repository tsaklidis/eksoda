"""SSRF-safe HTTPS fetcher for receipt pages (pure Python, requirements §15.1, TD §10).

Only reachable through a registered provider. Rules:

1. https, port 443, host exactly in the provider's allowlist.
2. Every DNS answer must be a public (globally routable) address.
3. The TCP connection goes to the validated IP (pinned) while TLS SNI and
   certificate checks use the hostname, so DNS rebinding cannot redirect it.
4. No redirects; unexpected statuses fail.
5. Connect/read timeouts plus an overall deadline.
6. Body capped *after* decompression; only text/html accepted.
7. Fixed request headers: no cookies, credentials or client headers; no proxies.
"""

import codecs
import ipaddress
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import certifi
import urllib3
from urllib3.exceptions import (
    ConnectTimeoutError,
    HTTPError,
    NewConnectionError,
    ProtocolError,
    ReadTimeoutError,
    SSLError,
)
from urllib3.exceptions import TimeoutError as Urllib3TimeoutError

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
from apps.receipts.links import ParsedUrl

USER_AGENT = "EksodaReceiptImporter/1.0"
CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class FetchLimits:
    connect_timeout: float = 5.0
    read_timeout: float = 15.0
    total_timeout: float = 30.0
    max_bytes: int = 2 * 1024 * 1024


@dataclass(frozen=True)
class FetchedDocument:
    body: bytes
    status: int = 200
    charset: str = "utf-8"

    def text(self) -> str:
        encoding = self.charset or "utf-8"
        try:
            codecs.lookup(encoding)
        except LookupError:
            raise FormatChanged(f"unknown charset {encoding!r}") from None
        return self.body.decode(encoding, errors="replace")


def is_public_address(ip: str) -> bool:
    """True only for globally routable unicast addresses."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # "::ffff:10.0.0.1" reaches 10.0.0.1: judge the embedded IPv4 address.
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    # is_global alone still lets through some multicast and reserved ranges.
    return (
        address.is_global
        and not address.is_multicast
        and not address.is_unspecified
        and not address.is_reserved
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_private
    )


def https_pool(ip: str, host: str, limits: FetchLimits) -> urllib3.HTTPSConnectionPool:
    """A one-connection pool to ``ip`` that verifies TLS for ``host``.

    Connecting to the already-validated IP (instead of letting urllib3 resolve ``host``
    again) is what stops DNS rebinding; SNI and the certificate check still use ``host``.
    """
    return urllib3.HTTPSConnectionPool(
        host=ip,
        port=443,
        server_hostname=host,
        assert_hostname=host,
        cert_reqs="CERT_REQUIRED",
        ca_certs=certifi.where(),
        timeout=urllib3.Timeout(connect=limits.connect_timeout, read=limits.read_timeout),
        retries=False,
        maxsize=1,
    )


# Injectable for tests: DNS lookup, connection pool and clock.
PoolFactory = Callable[[str, str, FetchLimits], Any]
Resolver = Callable[..., list]


class SafeFetcher:
    def __init__(
        self,
        limits: FetchLimits | None = None,
        *,
        resolver: Resolver = socket.getaddrinfo,
        pool_factory: PoolFactory = https_pool,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.limits = limits or FetchLimits()
        self._resolver = resolver
        self._pool_factory = pool_factory
        self._clock = clock

    def get(
        self,
        url: ParsedUrl,
        *,
        allowed_hosts: frozenset[str],
        accept_statuses: frozenset[int] = frozenset(),
    ) -> FetchedDocument:
        """Fetch an HTML page. Statuses in ``accept_statuses`` are returned, not raised, so a
        provider can interpret them (e.g. a provider that answers 418 for missing documents)."""
        self._check_target(url, allowed_hosts)
        ip = self._resolve(url.host)
        started = self._clock()
        pool = self._pool_factory(ip, url.host, self.limits)
        try:
            response = pool.urlopen(
                "GET",
                url.target,
                headers=self._headers(url.host),
                redirect=False,
                retries=False,
                preload_content=False,  # stream, so the size cap applies while reading
                decode_content=True,
                assert_same_host=False,  # the pool's host is the IP, not url.host
            )
            try:
                return self._read(response, started, accept_statuses)
            finally:
                response.close()
        except NewConnectionError as exc:  # subclass of ConnectTimeoutError: check first
            raise ProviderUnreachable(f"connection to {url.host} failed") from exc
        except SSLError as exc:
            raise ProviderUnreachable(f"TLS handshake with {url.host} failed") from exc
        except (ConnectTimeoutError, ReadTimeoutError, Urllib3TimeoutError, TimeoutError) as exc:
            raise ProviderTimeout(f"timeout talking to {url.host}") from exc
        except (ProtocolError, HTTPError, OSError) as exc:
            raise ProviderUnreachable(f"connection to {url.host} broke") from exc
        finally:
            pool.close()

    # --- steps ---------------------------------------------------------------------
    @staticmethod
    def _check_target(url: ParsedUrl, allowed_hosts: frozenset[str]) -> None:
        if url.scheme != "https" or url.port not in (None, 443):
            raise BlockedDestination("only https on port 443 is allowed")
        if url.host not in allowed_hosts:
            raise BlockedDestination(f"host {url.host} is not allowed for this provider")

    def _resolve(self, host: str) -> str:
        try:
            infos = self._resolver(host, 443, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError) as exc:
            raise ProviderUnreachable(f"DNS resolution failed for {host}") from exc
        addresses: list[str] = []
        for info in infos:
            ip = str(info[4][0]).split("%", 1)[0]  # drop an IPv6 zone id ("fe80::1%eth0")
            if ip not in addresses:
                addresses.append(ip)
        if not addresses:
            raise ProviderUnreachable(f"no addresses for {host}")
        # Every answer must be public, not just the one used: a mixed answer is suspicious.
        if not all(is_public_address(ip) for ip in addresses):
            raise BlockedDestination(f"{host} resolves to a non-public address")
        addresses.sort(key=lambda ip: ":" in ip)  # prefer IPv4, keep resolver order
        return addresses[0]

    @staticmethod
    def _headers(host: str) -> dict[str, str]:
        return {
            "Host": host,  # the connection goes to the IP, so name the site explicitly
            "User-Agent": USER_AGENT,
            "Accept": "text/html",
            "Accept-Language": "el-GR,el;q=0.9",
            "Accept-Encoding": "gzip",
        }

    def _read(self, response, started: float, accept: frozenset[int]) -> FetchedDocument:
        status = response.status
        if status != 200 and status not in accept:
            if status == 404:
                raise ReceiptNotFound("HTTP 404")
            if status in (408, 429) or status >= 500:
                raise ProviderHttpError(f"HTTP {status}")
            raise FormatChanged(f"unexpected HTTP status {status}")  # incl. redirects

        mime, _, params = (response.headers.get("Content-Type") or "").partition(";")
        mime = mime.strip().lower()
        if mime != "text/html":
            raise UnexpectedContentType(f"content type {mime or 'missing'}")
        declared = (response.headers.get("Content-Length") or "").strip()
        if declared.isdigit() and int(declared) > self.limits.max_bytes:
            raise ResponseTooLarge(f"declared length {declared}")

        # Count decompressed bytes: a small gzip body can expand far beyond the limit.
        chunks: list[bytes] = []
        size = 0
        for chunk in response.stream(CHUNK_SIZE, decode_content=True):
            size += len(chunk)
            if size > self.limits.max_bytes:
                raise ResponseTooLarge("body exceeds the size limit")
            if self._clock() - started > self.limits.total_timeout:
                raise ProviderTimeout("overall deadline exceeded")
            chunks.append(chunk)

        return FetchedDocument(body=b"".join(chunks), status=status, charset=_charset(params))


def _charset(params: str) -> str:
    for param in params.split(";"):
        name, _, value = param.strip().partition("=")
        if name.lower() == "charset" and value:
            return value.strip("\"' ").lower()
    return "utf-8"
