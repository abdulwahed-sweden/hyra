"""Admin configuration for queue models."""
from django.contrib import admin

from .models import QueueConfig, QueueEntry


@admin.register(QueueConfig)
class QueueConfigAdmin(admin.ModelAdmin):
    list_display = ["listing", "queue_type", "require_bankid", "min_credit_score"]
    list_filter = ["queue_type", "require_bankid"]


@admin.register(QueueEntry)
class QueueEntryAdmin(admin.ModelAdmin):
    list_display = [
        "applicant_name", "listing", "status", "queue_points",
        "rank_position", "rank_score", "applied_at",
    ]
    list_filter = ["status"]
    search_fields = ["applicant_name", "applicant_email"]
    raw_id_fields = ["listing"]
