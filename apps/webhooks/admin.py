from django.contrib import admin
from .models import WebhookEndpoint, WebhookEvent


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ["landlord", "url", "is_active", "created_at"]
    list_filter = ["is_active"]


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ["event_type", "endpoint", "status", "attempts", "created_at"]
    list_filter = ["status", "event_type"]
    readonly_fields = ["payload", "last_error"]
