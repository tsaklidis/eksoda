"""Error envelope and base API errors (TD §6.2).

Every error response has the shape ``{"error": {"code", "message", "details"}}``.
Codes are stable and documented; messages are safe to show to users.
"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404, JsonResponse
from rest_framework import exceptions, status
from rest_framework.views import exception_handler as drf_exception_handler

# DRF default codes that are renamed in the public contract.
_CODE_ALIASES = {
    "throttled": "rate_limited",
    "invalid": "validation_error",
    "parse_error": "invalid_request",  # malformed or oversized JSON body
}


class ApiError(exceptions.APIException):
    """Base class for domain errors. Subclasses set status_code, default_code, default_detail."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "bad_request"
    default_detail = "The request could not be processed."

    def __init__(self, detail=None, code=None, details: dict | None = None):
        super().__init__(detail=detail, code=code)
        self.details = details or {}


class HouseholdRequired(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "household_required"
    default_detail = "You belong to several households: select one with the X-Household-ID header."


class HouseholdForbidden(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "household_forbidden"
    default_detail = "You do not have access to this household."


def envelope(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def exception_handler(exc, context):
    """DRF exception handler that wraps every handled error in the envelope."""
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # unhandled: Django's handler500 answers with the envelope

    if isinstance(exc, exceptions.ValidationError):
        code, message, details = "validation_error", "Invalid input.", response.data
    else:
        code, message = _code_and_message(exc)
        details = dict(getattr(exc, "details", {}) or {})
        if isinstance(exc, exceptions.Throttled) and exc.wait is not None:
            details["retry_after_seconds"] = int(exc.wait)

    response.data = envelope(_CODE_ALIASES.get(code, code), message, details)
    return response


def _code_and_message(exc: exceptions.APIException) -> tuple[str, str]:
    detail = exc.detail
    if isinstance(detail, dict):  # e.g. simplejwt InvalidToken
        code = str(detail.get("code") or exc.default_code)
        message = str(detail.get("detail") or exc.default_detail)
        return code, message
    if isinstance(detail, list):
        detail = detail[0] if detail else exc.default_detail
    code = getattr(detail, "code", None) or exc.default_code
    return str(code), str(detail)


def bad_request(request, exception=None):
    """Django-level 400s, e.g. a body over DATA_UPLOAD_MAX_MEMORY_SIZE (16 KB)."""
    return JsonResponse(envelope("invalid_request", "The request could not be read."), status=400)


def not_found(request, exception=None):
    return JsonResponse(envelope("not_found", "Not found."), status=404)


def server_error(request):
    return JsonResponse(envelope("internal_error", "An internal error occurred."), status=500)
