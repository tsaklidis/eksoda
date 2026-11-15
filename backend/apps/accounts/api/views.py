"""Authentication endpoints (requirements §12.1)."""

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts import services
from apps.accounts.api.serializers import (
    LoginSerializer,
    LogoutSerializer,
    PasswordChangeSerializer,
    RegisterResponseSerializer,
    RegisterSerializer,
    UserSerializer,
)
from apps.accounts.errors import InvalidToken
from apps.accounts.throttles import LoginIpRateThrottle, LoginRateThrottle, RegisterRateThrottle


@extend_schema(tags=["auth"])
class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [RegisterRateThrottle]

    @extend_schema(request=RegisterSerializer, responses={201: RegisterResponseSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = services.register_user(
            email=data["email"],
            password=data["password"],
            display_name=data.get("display_name", ""),
            invite_code=data.get("invite_code") or None,
        )
        body = {"user": UserSerializer(user).data, "tokens": services.issue_tokens(user)}
        return Response(body, status=status.HTTP_201_CREATED)


@extend_schema(tags=["auth"])
class LoginView(TokenObtainPairView):
    """Exchange email and password for an access/refresh token pair."""

    serializer_class = LoginSerializer
    throttle_classes = [LoginIpRateThrottle, LoginRateThrottle]


@extend_schema(tags=["auth"])
class RefreshView(TokenRefreshView):
    """Exchange a refresh token for a new pair. The old refresh token is revoked."""


@extend_schema(tags=["auth"])
class LogoutView(APIView):
    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
        except TokenError as exc:
            raise InvalidToken() from exc
        if str(token.get("user_id")) != str(request.user.pk):
            raise InvalidToken()
        token.blacklist()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["auth"])
class MeView(APIView):
    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


@extend_schema(tags=["auth"])
class PasswordChangeView(APIView):
    @extend_schema(request=PasswordChangeSerializer, responses={204: None})
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        services.change_password(
            user=request.user, new_password=serializer.validated_data["new_password"]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
