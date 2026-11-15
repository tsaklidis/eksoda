import json
import logging
import sys

import pytest
from django.conf import settings
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.authentication import JWTAuthentication
from apps.common.logging import (
    REDACTED_URL,
    ContextFilter,
    JsonFormatter,
    RedactFilter,
    bind_log_context,
    clear_log_context,
    get_log_context,
)
from config.celery import _bind_task_log_context, _clear_task_log_context

RECEIPT_URL = "https://einvoice.impact.gr/p/EL094062259/" + "A" * 40 + "/" + "B" * 32


@pytest.fixture(autouse=True)
def _reset_context():
    clear_log_context()
    yield
    clear_log_context()


def make_record(msg, *args):
    return logging.LogRecord("test", logging.INFO, __file__, 1, msg, args, None)


def test_redact_filter_removes_urls_from_args():
    record = make_record("fetched %s ok", RECEIPT_URL)
    assert RedactFilter().filter(record) is True
    assert record.getMessage() == f"fetched {REDACTED_URL} ok"
    assert "einvoice" not in record.getMessage()


@pytest.mark.parametrize("formatter", [logging.Formatter("%(message)s"), JsonFormatter()])
def test_redact_filter_removes_urls_from_tracebacks(formatter):
    try:
        raise ValueError(f"cannot open {RECEIPT_URL}")
    except ValueError:
        record = logging.LogRecord("test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    RedactFilter().filter(record)
    output = formatter.format(record)
    assert "ValueError: cannot open <url>" in output
    assert "einvoice" not in output


def test_redact_filter_leaves_other_messages_untouched():
    record = make_record("imported %d lines", 5)
    RedactFilter().filter(record)
    assert record.args == (5,)
    assert record.getMessage() == "imported 5 lines"


def test_context_filter_adds_bound_fields():
    bind_log_context(user_id="u1", household_id=None)
    record = make_record("hello")
    ContextFilter().filter(record)
    assert record.user_id == "u1"
    assert record.household_id == "-"
    assert record.request_id == "-"


def test_json_formatter_from_settings_includes_context():
    bind_log_context(request_id="req-1", job_id="job-9")
    fmt = settings.LOGGING["formatters"]["json"]
    formatter = JsonFormatter(fmt["fmt"], rename_fields=fmt["rename_fields"])
    record = make_record("visit %s", RECEIPT_URL)
    ContextFilter().filter(record)
    RedactFilter().filter(record)
    payload = json.loads(formatter.format(record))
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "req-1"
    assert payload["job_id"] == "job-9"
    assert payload["message"] == f"visit {REDACTED_URL}"


@pytest.mark.django_db
def test_request_id_is_generated_and_echoed(client):
    response = client.get("/healthz")
    assert len(response["X-Request-ID"]) == 32


@pytest.mark.django_db
def test_valid_incoming_request_id_is_kept_and_invalid_replaced(client):
    assert client.get("/healthz", HTTP_X_REQUEST_ID="abc-123")["X-Request-ID"] == "abc-123"
    replaced = client.get("/healthz", HTTP_X_REQUEST_ID="bad id with spaces")["X-Request-ID"]
    assert replaced != "bad id with spaces"
    assert get_log_context() == {}  # middleware resets the context after the request


@pytest.mark.django_db
def test_jwt_authentication_binds_user_id(owner):
    token = RefreshToken.for_user(owner.user).access_token
    request = Request(APIRequestFactory().get("/", HTTP_AUTHORIZATION=f"Bearer {token}"))
    user, _ = JWTAuthentication().authenticate(request)
    assert get_log_context()["user_id"] == str(user.pk)
    assert JWTAuthentication().authenticate(Request(APIRequestFactory().get("/"))) is None


def test_celery_signals_bind_and_clear_task_context():
    _bind_task_log_context(task_id="t-1")
    assert get_log_context() == {"task_id": "t-1"}
    _clear_task_log_context()
    assert get_log_context() == {}
