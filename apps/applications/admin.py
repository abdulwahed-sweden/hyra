"""Admin configuration for applications."""
from django.contrib import admin

from .models import Application


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = [
        "applicant_name", "listing", "status",
        "monthly_income_sek", "submitted_at",
    ]
    list_filter = ["status"]
    search_fields = ["applicant_name", "applicant_email"]
    raw_id_fields = ["listing"]
