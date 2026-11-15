"""Household membership and invitation rules (requirements §5, TD §7.2)."""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.households.errors import (
    AlreadyMember,
    InvalidInvitation,
    InvitationNotPending,
    LastOwner,
    OwnerRequired,
)
from apps.households.models import Household, HouseholdInvitation, HouseholdMember

Role = HouseholdMember.Role


def hash_invitation_code(code: str) -> str:
    """Codes are random and high-entropy, so a plain SHA-256 is sufficient."""
    return hashlib.sha256(code.strip().encode()).hexdigest()


@transaction.atomic
def create_household_with_owner(*, user, name: str) -> Household:
    household = Household.objects.create(name=name)
    HouseholdMember.objects.create(household=household, user=user, role=Role.OWNER)
    return household


def get_membership_or_404(user, household_id) -> HouseholdMember:
    """The caller's membership in a household. Non-members get 404 (not 403)."""
    membership = (
        HouseholdMember.objects.select_related("household")
        .filter(user=user, household_id=household_id)
        .first()
    )
    if membership is None:
        raise NotFound()
    return membership


def require_owner(membership: HouseholdMember) -> None:
    if membership.role != Role.OWNER:
        raise OwnerRequired()


def create_invitation(
    *, household: Household, created_by, role: str = Role.MEMBER
) -> tuple[HouseholdInvitation, str]:
    """Create an invitation and return it with the plain code (shown only once)."""
    code = secrets.token_urlsafe(12)
    invitation = HouseholdInvitation.objects.create(
        household=household,
        code_hash=hash_invitation_code(code),
        role=role,
        created_by=created_by,
        expires_at=timezone.now() + timedelta(days=settings.INVITATION_TTL_DAYS),
    )
    return invitation, code


def revoke_invitation(invitation: HouseholdInvitation) -> HouseholdInvitation:
    if invitation.status != HouseholdInvitation.Status.PENDING:
        raise InvitationNotPending()
    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at", "updated_at"])
    return invitation


def lock_pending_invitation(code: str) -> HouseholdInvitation:
    """Lock a pending invitation by code. Must run inside a transaction."""
    invitation = (
        HouseholdInvitation.objects.select_for_update()
        .select_related("household")
        .filter(code_hash=hash_invitation_code(code))
        .first()
    )
    if invitation is None or invitation.status != HouseholdInvitation.Status.PENDING:
        raise InvalidInvitation()
    return invitation


@transaction.atomic
def accept_invitation(*, code: str, user) -> HouseholdMember:
    invitation = lock_pending_invitation(code)
    if HouseholdMember.objects.filter(household=invitation.household, user=user).exists():
        raise AlreadyMember()  # the invitation stays usable for someone else
    try:
        with transaction.atomic():  # savepoint: a concurrent join may win the race
            membership = HouseholdMember.objects.create(
                household=invitation.household, user=user, role=invitation.role
            )
    except IntegrityError:
        raise AlreadyMember() from None
    invitation.accepted_by = user
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_by", "accepted_at", "updated_at"])
    return membership


@transaction.atomic
def remove_member(*, actor: HouseholdMember, target: HouseholdMember) -> None:
    """Owners may remove anyone; members may only remove themselves (leave)."""
    if actor.pk != target.pk:
        require_owner(actor)
    # Lock the owner rows: two owners removing each other at the same time must not
    # both pass the check and leave the household without an owner.
    owners = list(
        HouseholdMember.objects.select_for_update().filter(
            household_id=target.household_id, role=Role.OWNER
        )
    )
    if target.role == Role.OWNER and len(owners) <= 1:
        raise LastOwner()
    target.delete()
