"""Request/task log context and URL redaction (TD §16).

Receipt URLs work as bearer credentials, so ``RedactFilter`` removes any URL from
log messages as a safety net. Code should log hosts and fingerprints instead.
"""

import logging
import re
import uuid
from contextvars import ContextVar

from pythonjsonlogger.json import JsonFormatter as BaseJsonFormatter

_LOG_CONTEXT: ContextVar[dict[str, str] | None] = ContextVar("log_context", default=None)
_CONTEXT_FIELDS = ("request_id", "user_id", "household_id", "task_id", "job_id", "provider")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
REDACTED_URL = "<url>"


def bind_log_context(**values) -> None:
    """Add values (e.g. user_id) to the log context of the current request or task."""
    current = _LOG_CONTEXT.get() or {}
    _LOG_CONTEXT.set({**current, **{k: str(v) for k, v in values.items() if v is not None}})


def clear_log_context() -> None:
    _LOG_CONTEXT.set(None)


def get_log_context() -> dict[str, str]:
    return dict(_LOG_CONTEXT.get() or {})


def redact_urls(text: str) -> str:
    return _URL_RE.sub(REDACTED_URL, text)


class ContextFilter(logging.Filter):
    """Copies the bound context onto every record (``-`` when unknown)."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = _LOG_CONTEXT.get() or {}
        for field in _CONTEXT_FIELDS:
            if not hasattr(record, field):
                setattr(record, field, context.get(field, "-"))
        return True


class RedactFilter(logging.Filter):
    """Replaces URLs in the rendered message and in tracebacks, so receipt links never
    reach the logs (an exception message may quote the URL it failed on).

    The traceback is formatted and redacted into ``exc_text``, which standard formatters
    print instead of formatting ``exc_info`` again. ``exc_info`` itself is kept for
    Sentry, which reads the record after the handlers and scrubs its own events.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = redact_urls(message)
        if redacted != message:
            record.msg, record.args = redacted, None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact_urls(record.exc_text)
        return True


class JsonFormatter(BaseJsonFormatter):
    """python-json-logger formats ``exc_info`` itself (ignoring ``exc_text``), so the
    traceback it renders is redacted here."""

    def formatException(self, ei) -> str:
        return redact_urls(super().formatException(ei))


class RequestContextMiddleware:
    """Binds a request id (from a valid ``X-Request-ID`` or a new UUID) and echoes it back."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        token = _LOG_CONTEXT.set({"request_id": request_id})
        try:
            response = self.get_response(request)
        finally:
            _LOG_CONTEXT.reset(token)
        response["X-Request-ID"] = request_id
        return response
