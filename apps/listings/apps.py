from django.apps import AppConfig


class ListingsConfig(AppConfig):
    """Configuration for the listings application — core property domain."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.listings"
    verbose_name = "Bostadsannonser"
