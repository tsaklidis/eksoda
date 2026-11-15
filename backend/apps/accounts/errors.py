from rest_framework import status

from apps.common.errors import ApiError


class InviteRequired(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invite_required"
    default_detail = "Registration requires a household invitation code."


class InvalidToken(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_token"
    default_detail = "The refresh token is invalid, expired or already revoked."
