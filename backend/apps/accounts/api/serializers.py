from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import User
from apps.households.models import HouseholdMember


class MembershipSerializer(serializers.ModelSerializer):
    household_id = serializers.UUIDField(source="household.id", read_only=True)
    household_name = serializers.CharField(source="household.name", read_only=True)

    class Meta:
        model = HouseholdMember
        fields = ["household_id", "household_name", "role", "joined_at"]
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "memberships", "created_at"]
        read_only_fields = fields

    def get_memberships(self, user: User) -> list[dict]:
        memberships = user.memberships.select_related("household").order_by("joined_at")
        return MembershipSerializer(memberships, many=True).data


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    display_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    invite_code = serializers.CharField(
        max_length=64, required=False, allow_blank=True, write_only=True
    )

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs: dict) -> dict:
        candidate = User(email=attrs["email"], display_name=attrs.get("display_name", ""))
        try:
            password_validation.validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs


class RegisterResponseSerializer(serializers.Serializer):
    user = UserSerializer()
    tokens = TokenPairSerializer()


class LoginSerializer(TokenObtainPairSerializer):
    """Email + password → token pair. The email is matched case-insensitively."""

    def validate(self, attrs: dict) -> dict:
        attrs[self.username_field] = str(attrs.get(self.username_field, "")).strip().lower()
        return super().validate(attrs)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate_old_password(self, value: str) -> str:
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("The current password is incorrect.")
        return value

    def validate_new_password(self, value: str) -> str:
        try:
            password_validation.validate_password(value, self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value
