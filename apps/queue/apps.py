from django.apps import AppConfig


# Renamed from QueueConfig to avoid clash with apps.queue.models.QueueConfig
class QueueAppConfig(AppConfig):
    """Configuration for the queue application — ranking and selection engine."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.queue"
    verbose_name = "Bostadskö"
