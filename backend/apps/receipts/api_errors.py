"""API errors of the receipt endpoints (requirements §6.2, §12.4).

Submission errors are raised by the pure URL layer as ReceiptError subclasses;
``for_submission_error`` turns them into API errors with the same stable codes.
"""

from rest_framework import status

from apps.common.errors import ApiError
from apps.receipts.errors import (
    ErrorCode,
    InvalidUrl,
    ReceiptError,
    UnsupportedProvider,
    UnsupportedUrlFormat,
)


class InvalidReceiptUrl(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = ErrorCode.INVALID_URL.value
    default_detail = "The receipt link is not a valid https URL."


class UnsupportedReceiptProvider(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = ErrorCode.UNSUPPORTED_PROVIDER.value
    default_detail = "Receipts from this provider are not supported yet."


class UnsupportedReceiptUrlFormat(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = ErrorCode.UNSUPPORTED_URL_FORMAT.value
    default_detail = "This receipt link has an unexpected format."


class NotRetryable(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "not_retryable"
    default_detail = "Only failed imports can be retried."


_BY_CODE: dict[ErrorCode, type[ApiError]] = {
    ErrorCode.INVALID_URL: InvalidReceiptUrl,
    ErrorCode.UNSUPPORTED_PROVIDER: UnsupportedReceiptProvider,
    ErrorCode.UNSUPPORTED_URL_FORMAT: UnsupportedReceiptUrlFormat,
}


SUBMISSION_ERRORS = (InvalidUrl, UnsupportedProvider, UnsupportedUrlFormat)


def for_submission_error(exc: ReceiptError) -> ApiError:
    """The API error for a rejected submission (one of SUBMISSION_ERRORS), without the URL."""
    return _BY_CODE[exc.code]()
