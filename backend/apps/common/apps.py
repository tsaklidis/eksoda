from django.apps import AppConfig


class CommonConfig(AppConfig):
    name = "apps.common"
    label = "common"
    verbose_name = "Common"

    def ready(self) -> None:
        from apps.common import schema  # noqa: F401  registers OpenAPI extensions
