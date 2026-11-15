"""Optional Sentry error tracking with personal-data scrubbing (requirements §16, TD §16).

Receipt URLs work as bearer credentials, and Sentry sees more than the logs do: raw log
records (before ``RedactFilter``), exception messages and request bodies. So events are
sent without local variables or request bodies (``send_default_pii`` is left at its
default, off; the option is deprecated), and every URL-shaped string left in an event or
breadcrumb is replaced with ``<url>``. The request's own path (an API route) is
kept. Events are tagged from the log context (request, task, job, household, provider).
"""

from typing import Any

from apps.common.logging import get_log_context, redact_urls

_TAGGED_CONTEXT = ("request_id", "task_id", "job_id", "household_id", "provider")
_DROPPED_REQUEST_KEYS = ("data", "query_string", "cookies", "env")
_DROPPED_HEADERS = {"authorization", "cookie", "referer", "x-forwarded-for", "x-real-ip"}


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_urls(value)
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(item) for item in value]
    return value


def scrub_event(event: dict, _hint: dict | None = None) -> dict:
    request = event.pop("request", None)
    event = _redact(event)
    if request:
        for key in _DROPPED_REQUEST_KEYS:
            request.pop(key, None)
        headers = request.get("headers") or {}
        request["headers"] = {
            name: redact_urls(value)
            for name, value in headers.items()
            if name.lower() not in _DROPPED_HEADERS
        }
        event["request"] = request  # url is scheme, host and path of our own API
    tags = event.setdefault("tags", {})
    for field, value in get_log_context().items():
        if field in _TAGGED_CONTEXT:
            tags.setdefault(field, value)
    return event


def scrub_breadcrumb(breadcrumb: dict, _hint: dict | None = None) -> dict:
    return _redact(breadcrumb)


def init_sentry(dsn: str, *, environment: str, release: str | None = None, **options) -> None:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release or None,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
        before_send=scrub_event,
        before_breadcrumb=scrub_breadcrumb,
        **options,
    )
