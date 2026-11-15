from rest_framework import status

from apps.common.errors import ApiError


class OwnerRequired(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "owner_required"
    default_detail = "Only a household owner can do this."


class LastOwner(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "last_owner"
    default_detail = "A household must keep at least one owner."


class AlreadyMember(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "already_member"
    default_detail = "You are already a member of this household."


class InvalidInvitation(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_invitation"
    default_detail = "The invitation code is invalid, expired, revoked or already used."


class InvitationNotPending(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "invitation_not_pending"
    default_detail = "Only pending invitations can be revoked."
