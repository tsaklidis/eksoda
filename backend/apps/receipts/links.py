"""Validation of submitted receipt URLs (pure Python, requirements §6.2, TD §9.3)."""

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from apps.receipts.errors import InvalidUrl

MAX_URL_LENGTH = 2048
_LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


def _valid_host(host: str) -> bool:
    """A DNS name made of valid labels, or an IP address literal."""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    return len(host) <= 253 and all(_LABEL_RE.match(label) for label in host.split("."))


@dataclass(frozen=True)
class ParsedUrl:
    """A syntactically safe https URL: lowercase IDNA host, no userinfo/fragment/odd port."""

    scheme: str
    host: str
    port: int | None
    path: str
    query: str

    @property
    def target(self) -> str:
        """The request target (path and query) sent to the server."""
        return f"{self.path}?{self.query}" if self.query else self.path

    def geturl(self) -> str:
        netloc = self.host if self.port is None else f"{self.host}:{self.port}"
        return urlunsplit((self.scheme, netloc, self.path, self.query, ""))


def parse_submitted_url(raw: object) -> ParsedUrl:
    if not isinstance(raw, str):
        raise InvalidUrl("not a string")
    text = raw.strip()
    if not text or len(text) > MAX_URL_LENGTH:
        raise InvalidUrl("empty or too long")
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        raise InvalidUrl("contains whitespace or control characters")

    parts = urlsplit(text)
    if parts.scheme.lower() != "https":
        raise InvalidUrl("scheme must be https")
    if parts.username is not None or parts.password is not None:
        raise InvalidUrl("userinfo is not allowed")
    if parts.fragment:
        raise InvalidUrl("fragments are not allowed")
    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidUrl("invalid port") from exc
    if port not in (None, 443):
        raise InvalidUrl("only port 443 is allowed")
    host = parts.hostname or ""
    if not host:
        raise InvalidUrl("missing host")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InvalidUrl("invalid host name") from exc
    if not _valid_host(host):
        raise InvalidUrl("invalid host name")
    return ParsedUrl(
        scheme="https", host=host, port=port, path=parts.path or "/", query=parts.query
    )
