"""Registration, token and password rules (requirements §5, §12.1; TD §7.2)."""

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.errors import InviteRequired
from apps.accounts.models import User
from apps.households import services as households


def default_household_name(user: User) -> str:
    owner = user.display_name or user.email.split("@", 1)[0]
    return f"{owner}'s household"


@transaction.atomic
def register_user(
    *, email: str, password: str, display_name: str = "", invite_code: str | None = None
) -> User:
    """Create a user.

    With an invitation code the user joins that household. Without one, a personal
    household is created only when registration is open; otherwise InviteRequired.
    The invitation is validated (and locked) before the user is created.
    """
    if invite_code:
        households.lock_pending_invitation(invite_code)  # fail before creating the user
        user = _create_user(email=email, password=password, display_name=display_name)
        households.accept_invitation(code=invite_code, user=user)
        return user

    if not settings.REGISTRATION_OPEN:
        raise InviteRequired()
    user = _create_user(email=email, password=password, display_name=display_name)
    households.create_household_with_owner(user=user, name=default_household_name(user))
    return user


def issue_tokens(user: User) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


@transaction.atomic
def change_password(*, user: User, new_password: str) -> None:
    """Set the password and revoke every refresh token the user holds."""
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    for token in OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True):
        BlacklistedToken.objects.get_or_create(token=token)  # a concurrent logout may win


def _create_user(*, email: str, password: str, display_name: str) -> User:
    """Create the user; a concurrent registration with the same email is a 400, not a 500."""
    try:
        with transaction.atomic():
            return User.objects.create_user(
                email=email, password=password, display_name=display_name
            )
    except IntegrityError:
        raise ValidationError({"email": ["A user with this email already exists."]}) from None
