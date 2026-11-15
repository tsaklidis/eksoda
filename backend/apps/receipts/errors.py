"""Receipt import errors (pure Python, requirements §6.4, TD §9.4).

Every error has a stable ``code`` (shown to users), a ``public_message`` (safe to
show), a retry policy, and an internal ``detail`` for logs. Details must never
contain full receipt URLs.
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_URL = "invalid_url"
    UNSUPPORTED_PROVIDER = "unsupported_provider"
    UNSUPPORTED_URL_FORMAT = "unsupported_url_format"
    PROVIDER_UNREACHABLE = "provider_unreachable"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_ERROR = "provider_error"
    RECEIPT_NOT_FOUND = "receipt_not_found"
    BLOCKED_DESTINATION = "blocked_destination"
    RESPONSE_TOO_LARGE = "response_too_large"
    UNEXPECTED_CONTENT_TYPE = "unexpected_content_type"
    PROVIDER_FORMAT_CHANGED = "provider_format_changed"
    INCONSISTENT_SOURCE = "inconsistent_source"
    INTERNAL_ERROR = "internal_error"


class RetryPolicy(StrEnum):
    TRANSIENT = "transient"  # network or provider trouble: retried
    NOT_FOUND = "not_found"  # retried too: a receipt can appear at the provider after a delay
    INTERNAL = "internal"
    NONE = "none"


class ReceiptError(Exception):
    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    retry: RetryPolicy = RetryPolicy.NONE
    public_message: str = "The receipt could not be processed."

    def __init__(self, detail: str = ""):
        self.detail = detail
        super().__init__(f"{self.code}: {detail}" if detail else str(self.code))


# --- Submission errors: rejected by the API, never retried --------------------------
class InvalidUrl(ReceiptError):
    code = ErrorCode.INVALID_URL
    public_message = "The receipt link is not a valid https URL."


class UnsupportedProvider(ReceiptError):
    code = ErrorCode.UNSUPPORTED_PROVIDER
    public_message = "Receipts from this provider are not supported yet."


class UnsupportedUrlFormat(ReceiptError):
    code = ErrorCode.UNSUPPORTED_URL_FORMAT
    public_message = "This receipt link has an unexpected format."


# --- Fetch and parse errors -----------------------------------------------------
class ProviderUnreachable(ReceiptError):
    code = ErrorCode.PROVIDER_UNREACHABLE
    retry = RetryPolicy.TRANSIENT
    public_message = "The receipt provider could not be reached."


class ProviderTimeout(ReceiptError):
    code = ErrorCode.PROVIDER_TIMEOUT
    retry = RetryPolicy.TRANSIENT
    public_message = "The receipt provider did not respond in time."


class ProviderHttpError(ReceiptError):
    code = ErrorCode.PROVIDER_ERROR
    retry = RetryPolicy.TRANSIENT
    public_message = "The receipt provider returned an error."


class BlockedDestination(ReceiptError):
    code = ErrorCode.BLOCKED_DESTINATION
    public_message = "The receipt address is not allowed."


class ResponseTooLarge(ReceiptError):
    code = ErrorCode.RESPONSE_TOO_LARGE
    public_message = "The receipt page is too large."


class UnexpectedContentType(ReceiptError):
    code = ErrorCode.UNEXPECTED_CONTENT_TYPE
    public_message = "The receipt provider returned an unexpected kind of response."


class ReceiptNotFound(ReceiptError):
    code = ErrorCode.RECEIPT_NOT_FOUND
    retry = RetryPolicy.NOT_FOUND
    public_message = "The receipt is not available from the provider (yet)."


class FormatChanged(ReceiptError):
    code = ErrorCode.PROVIDER_FORMAT_CHANGED
    public_message = "The receipt page format is not recognized."


class InconsistentSource(ReceiptError):
    code = ErrorCode.INCONSISTENT_SOURCE
    public_message = "The receipt page contains inconsistent data."


class InternalError(ReceiptError):
    code = ErrorCode.INTERNAL_ERROR
    retry = RetryPolicy.INTERNAL
    public_message = "An internal error occurred while importing the receipt."
