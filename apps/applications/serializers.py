"""Serializers for the applications API."""
from rest_framework import serializers

from django_pyforge.serializers import RustSerializerMixin

from .models import Application


# [M11] Explicit fields instead of __all__
class ApplicationSerializer(RustSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = [
            "id", "listing", "applicant_name", "applicant_email",
            "phone_number", "message", "monthly_income_sek",
            "household_size", "status", "submitted_at", "updated_at",
        ]
        read_only_fields = ["submitted_at", "updated_at"]
