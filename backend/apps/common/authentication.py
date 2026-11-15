from rest_framework_simplejwt import authentication

from apps.common.logging import bind_log_context


class JWTAuthentication(authentication.JWTAuthentication):
    """simplejwt authentication that also binds the user id into the log context."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            bind_log_context(user_id=str(result[0].pk))
        return result
