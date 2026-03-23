from django.apps import AppConfig


class SearchConfig(AppConfig):
    """Configuration for the search application — Elasticsearch integration."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.search"
    verbose_name = "Sökning"
