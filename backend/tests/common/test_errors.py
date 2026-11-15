import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import reverse
from rest_framework import exceptions

from apps.common.errors import (
    ApiError,
    bad_request,
    exception_handler,
    not_found,
    server_error,
)
from tests.utils import error_code

pytestmark = pytest.mark.django_db


def test_not_authenticated_envelope(api_client):
    response = api_client.get(reverse("api-v1:auth-me"))
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "not_authenticated",
            "message": "Authentication credentials were not provided.",
            "details": {},
        }
    }


def test_validation_error_envelope_lists_fields(api_client):
    response = api_client.post(reverse("api-v1:auth-register"), {}, format="json")
    body = response.json()["error"]
    assert response.status_code == 400
    assert body["code"] == "validation_error"
    assert {"email", "password"} <= set(body["details"])


def test_invalid_jwt_uses_simplejwt_code(api_client):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")
    response = api_client.get(reverse("api-v1:auth-me"))
    assert response.status_code == 401
    assert error_code(response) == "token_not_valid"


def test_method_not_allowed(owner_client):
    response = owner_client.delete(reverse("api-v1:auth-me"))
    assert response.status_code == 405
    assert error_code(response) == "method_not_allowed"


def test_api_error_carries_details():
    response = exception_handler(ApiError("Boom.", details={"field": 1}), {})
    assert response.status_code == 400
    assert response.data == {
        "error": {"code": "bad_request", "message": "Boom.", "details": {"field": 1}}
    }


def test_list_detail_validation_error():
    response = exception_handler(exceptions.ValidationError(["Bad."]), {})
    assert response.data["error"]["code"] == "validation_error"
    assert response.data["error"]["details"] == ["Bad."]


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [(Http404(), 404, "not_found"), (PermissionDenied(), 403, "permission_denied")],
)
def test_django_exceptions_are_mapped(exc, status, code):
    response = exception_handler(exc, {})
    assert response.status_code == status
    assert response.data["error"]["code"] == code


def test_unhandled_exceptions_fall_through_to_handler500():
    assert exception_handler(ValueError("boom"), {}) is None


def test_json_handlers(rf):
    assert server_error(rf.get("/")).status_code == 500
    assert b'"internal_error"' in server_error(rf.get("/")).content
    assert not_found(rf.get("/x")).status_code == 404
    assert b'"invalid_request"' in bad_request(rf.get("/")).content


def test_oversized_body_returns_the_json_envelope(client):
    body = '{"email": "a@example.com", "password": "' + "x" * 20000 + '"}'
    response = client.post("/api/v1/auth/login", body, content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_unknown_url_returns_json_404(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
