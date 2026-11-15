from rest_framework import serializers

from apps.households.models import (
    Household,
    HouseholdInvitation,
    HouseholdMember,
    validate_currency,
)


class HouseholdSerializer(serializers.ModelSerializer):
    role = serializers.CharField(read_only=True, help_text="Your role in this household.")
    # Declared explicitly so lowercase input is uppercased before validation (an
    # implicit model field would run the model's validator first and reject it).
    default_currency = serializers.CharField(max_length=3, required=False)

    class Meta:
        model = Household
        fields = ["id", "name", "default_currency", "timezone", "role", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_default_currency(self, value: str) -> str:
        value = value.upper()
        validate_currency(value)
        return value


class MemberSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    display_name = serializers.CharField(source="user.display_name", read_only=True)

    class Meta:
        model = HouseholdMember
        fields = ["id", "user_id", "email", "display_name", "role", "joined_at"]
        read_only_fields = fields


class InvitationSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=HouseholdInvitation.Status.choices, read_only=True)
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = HouseholdInvitation
        fields = [
            "id",
            "role",
            "status",
            "expires_at",
            "created_by_email",
            "accepted_at",
            "revoked_at",
            "created_at",
        ]
        read_only_fields = [f for f in fields if f != "role"]


class CreatedInvitationSerializer(InvitationSerializer):
    code = serializers.CharField(
        read_only=True, help_text="Share this code with the invitee. It is shown only once."
    )

    class Meta(InvitationSerializer.Meta):
        fields = [*InvitationSerializer.Meta.fields, "code"]
        read_only_fields = fields


class JoinSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64, trim_whitespace=True)
