"""Maps hosts to providers (pure Python, TD §9.3)."""

from collections.abc import Iterable

from apps.receipts.errors import UnsupportedProvider, UnsupportedUrlFormat
from apps.receipts.links import parse_submitted_url
from apps.receipts.providers.base import Provider, UrlIdentity


class ProviderRegistry:
    def __init__(self, providers: Iterable[Provider] = ()):
        self._by_code: dict[str, Provider] = {}
        self._by_host: dict[str, Provider] = {}
        for provider in providers:
            if provider.code in self._by_code:
                raise ValueError(f"provider {provider.code!r} is already registered")
            self._by_code[provider.code] = provider
            for host in provider.hosts:
                if host in self._by_host:
                    raise ValueError(f"host {host!r} is already registered")
                self._by_host[host] = provider

    @property
    def codes(self) -> list[str]:
        return sorted(self._by_code)

    def get(self, code: str) -> Provider:
        try:
            return self._by_code[code]
        except KeyError:
            raise UnsupportedProvider(f"no provider with code {code!r}") from None

    def resolve_url(self, raw: object) -> tuple[Provider, UrlIdentity]:
        """Validate a submitted URL and find its provider (InvalidUrl, UnsupportedProvider or
        UnsupportedUrlFormat otherwise)."""
        url = parse_submitted_url(raw)
        provider = self._by_host.get(url.host)
        if provider is None:
            raise UnsupportedProvider(f"host {url.host}")
        identity = provider.recognize(url)
        if identity is None:
            raise UnsupportedUrlFormat(f"unrecognized {provider.code} URL")
        return provider, identity
