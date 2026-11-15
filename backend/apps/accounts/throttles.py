import hashlib
from collections.abc import Mapping
from functools import wraps

from django.http import HttpResponse
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """Limits attempts per (client IP, email) pair."""

    scope = "login"

    def get_cache_key(self, request, view):
        # Throttles run before validation: the body may be a JSON array or a string.
        data = request.data if isinstance(request.data, Mapping) else {}
        email = str(data.get("email", "")).strip().lower()
        ident = hashlib.sha256(f"{self.get_ident(request)}|{email}".encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LoginIpRateThrottle(AnonRateThrottle):
    """Limits attempts per client IP, whatever the email (stops spraying many emails)."""

    scope = "login_ip"


class RegisterRateThrottle(AnonRateThrottle):
    scope = "register"


class AdminLoginRateThrottle(SimpleRateThrottle):
    """Limits admin login attempts per client IP (the admin is public behind the proxy)."""

    scope = "admin_login"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


def throttle_admin_login(login_view):
    """Wraps ``AdminSite.login``: a POST over the rate answers 429 without checking the
    password. DRF throttles work on the Django request too (they read only ``META``)."""

    @wraps(login_view)
    def view(request, *args, **kwargs):
        if request.method == "POST" and not AdminLoginRateThrottle().allow_request(request, None):
            return HttpResponse(
                "Too many login attempts. Try again later.", status=429, content_type="text/plain"
            )
        return login_view(request, *args, **kwargs)

    return view
