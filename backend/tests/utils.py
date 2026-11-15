from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


def client_for(user) -> APIClient:
    """An API client authenticated as ``user`` with a fresh JWT access token."""
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def error_code(response) -> str:
    return response.json()["error"]["code"]
