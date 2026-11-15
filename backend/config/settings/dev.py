from .base import *

DEBUG = True

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]
# The browsable API and the admin authenticate with the session.
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [
    "apps.common.authentication.JWTAuthentication",
    "rest_framework.authentication.SessionAuthentication",
]

STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
