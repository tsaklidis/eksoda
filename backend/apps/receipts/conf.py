from django.conf import settings

from apps.receipts.fetching import FetchLimits, SafeFetcher


def fetch_limits() -> FetchLimits:
    return FetchLimits(
        connect_timeout=settings.FETCH_CONNECT_TIMEOUT,
        read_timeout=settings.FETCH_READ_TIMEOUT,
        total_timeout=settings.FETCH_TOTAL_TIMEOUT,
        max_bytes=settings.FETCH_MAX_BYTES,
    )


def default_fetcher() -> SafeFetcher:
    return SafeFetcher(fetch_limits())
