import logging

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from apps.common.logging import bind_log_context, clear_log_context
from apps.common.sentry import init_sentry, scrub_breadcrumb, scrub_event

RECEIPT_URL = "https://einvoice.impact.gr/p/EL094062259/" + "A" * 40 + "/" + "B" * 32
SECRET = "A" * 40


class MemoryTransport(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.events: list[dict] = []

    def capture_envelope(self, envelope):
        event = envelope.get_event()
        if event is not None:
            self.events.append(event)


@pytest.fixture
def sentry_events():
    transport = MemoryTransport()
    init_sentry("https://public@sentry.example.com/1", environment="test", transport=transport)
    clear_log_context()
    yield transport.events
    clear_log_context()
    sentry_sdk.get_client().close()
    sentry_sdk.init()  # no DSN: nothing is sent by later tests


def test_logged_errors_reach_sentry_without_the_url(sentry_events):
    bind_log_context(job_id="job-1", provider="impact", user_id="u-1")
    logger = logging.getLogger("apps.receipts.services.pipeline")
    logger.info("fetching %s", RECEIPT_URL)  # becomes a breadcrumb
    try:
        raise RuntimeError(f"cannot parse {RECEIPT_URL}")
    except RuntimeError:
        logger.exception("receipt import failed for %s", RECEIPT_URL)

    (event,) = sentry_events
    assert SECRET not in repr(event)
    assert event["tags"]["job_id"] == "job-1"
    assert event["tags"]["provider"] == "impact"
    assert "user_id" not in event["tags"]
    assert event["exception"]["values"][0]["value"] == "cannot parse <url>"
    assert all(
        "vars" not in frame for frame in event["exception"]["values"][0]["stacktrace"]["frames"]
    )
    assert any(crumb.get("message") == "fetching <url>" for crumb in event["breadcrumbs"]["values"])


def test_request_bodies_and_sensitive_headers_are_dropped():
    event = {
        "message": f"failed on {RECEIPT_URL}",
        "request": {
            "url": "https://eksoda.example.org/api/v1/receipts/import",
            "method": "POST",
            "data": {"url": RECEIPT_URL},
            "query_string": f"next={RECEIPT_URL}",
            "cookies": {"sessionid": "s"},
            "headers": {
                "Authorization": "Bearer t",
                "Referer": RECEIPT_URL,
                "User-Agent": "okhttp/4",
                "X-Note": f"see {RECEIPT_URL}",
            },
        },
    }
    scrubbed = scrub_event(event)
    request = scrubbed["request"]
    assert request["url"] == "https://eksoda.example.org/api/v1/receipts/import"
    assert set(request) == {"url", "method", "headers"}
    assert request["headers"] == {"User-Agent": "okhttp/4", "X-Note": "see <url>"}
    assert scrubbed["message"] == "failed on <url>"
    assert SECRET not in repr(scrubbed)


def test_breadcrumbs_are_redacted():
    crumb = {"category": "httplib", "data": {"url": RECEIPT_URL, "status": 200}}
    assert scrub_breadcrumb(crumb) == {
        "category": "httplib",
        "data": {"url": "<url>", "status": 200},
    }
