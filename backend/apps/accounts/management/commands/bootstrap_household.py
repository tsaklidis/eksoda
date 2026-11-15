"""Create the first household owner (requirements §5). Idempotent."""

import getpass
import os
import sys

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.households.models import Household, HouseholdMember
from apps.households.services import create_household_with_owner


class Command(BaseCommand):
    help = "Create a user (if needed) who owns a household with the given name."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--household", required=True, help="Household name")
        parser.add_argument(
            "--password-env",
            metavar="VAR",
            help="Read the new user's password from this environment variable.",
        )
        parser.add_argument(
            "--superuser",
            action="store_true",
            help="Also grant Django admin access (staff + superuser).",
        )

    def handle(self, *args, email: str, household: str, password_env: str | None, **options):
        email = email.strip().lower()
        name = household.strip()
        if not email or not name:
            raise CommandError("--email and --household must not be empty.")

        with transaction.atomic():
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                password = self._password(password_env)
                try:
                    password_validation.validate_password(password, User(email=email))
                except ValidationError as exc:
                    raise CommandError(" ".join(exc.messages)) from exc
                user = User.objects.create_user(email=email, password=password)
                self.stdout.write(f"Created user {email}.")
            else:
                self.stdout.write(f"User {email} already exists.")

            if options["superuser"] and not (user.is_staff and user.is_superuser):
                user.is_staff = user.is_superuser = True
                user.save(update_fields=["is_staff", "is_superuser", "updated_at"])
                self.stdout.write("Granted admin access.")

            owned = Household.objects.filter(
                name=name, members__user=user, members__role=HouseholdMember.Role.OWNER
            ).first()
            if owned is not None:
                self.stdout.write(f'Household "{name}" already exists ({owned.pk}).')
                return
            created = create_household_with_owner(user=user, name=name)
            self.stdout.write(self.style.SUCCESS(f'Created household "{name}" ({created.pk}).'))

    def _password(self, password_env: str | None) -> str:
        if password_env:
            password = os.environ.get(password_env, "")
            if not password:
                raise CommandError(f"Environment variable {password_env} is empty or not set.")
            return password
        if not sys.stdin.isatty():
            raise CommandError("No TTY: pass --password-env VAR to provide the password.")
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Password (again): "):
            raise CommandError("Passwords do not match.")
        return password
