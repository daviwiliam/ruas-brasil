from django.apps import AppConfig


class PortalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "portal"
    verbose_name = "Portal Ruas Brasil"

    def ready(self):
        from . import signals  # noqa: F401
