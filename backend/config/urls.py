from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.throttles import throttle_admin_login
from apps.common.health import healthz, readyz

admin.site.site_header = "Eksoda administration"
admin.site.login = throttle_admin_login(admin.site.login)

urlpatterns = [
    path(settings.ADMIN_PATH, admin.site.urls),
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    path("api/v1/", include(("config.api_urls", "api-v1"))),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

handler400 = "apps.common.errors.bad_request"
handler404 = "apps.common.errors.not_found"
handler500 = "apps.common.errors.server_error"
