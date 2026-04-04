"""Serializers for the queue API."""
from rest_framework import serializers

from django_pyforge.serializers import RustSerializerMixin

from .models import QueueConfig, QueueEntry


class QueueConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = QueueConfig
        fields = [
            "id", "listing", "queue_type", "require_bankid",
            "require_no_debt", "min_credit_score", "min_queue_points",
            "created_at",
        ]


# [M11, M12] Explicit fields + input validation for bounds
class QueueEntrySerializer(RustSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = QueueEntry
        fields = [
            "id", "listing", "applicant_name", "applicant_email",
            "monthly_income_sek", "household_size", "queue_points",
            "bankid_verified", "credit_score", "has_debt_records",
            "preferred_districts", "status", "disqualification_reason",
            "rank_score", "rank_position", "applied_at", "processed_at",
        ]
        read_only_fields = [
            "status", "disqualification_reason",
            "rank_score", "rank_position", "processed_at",
        ]

    def validate_monthly_income_sek(self, value):
        if value < 0:
            raise serializers.ValidationError("Income cannot be negative.")
        return value

    def validate_household_size(self, value):
        if value < 1 or value > 20:
            raise serializers.ValidationError("Household size must be between 1 and 20.")
        return value

    def validate_credit_score(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Credit score must be between 0 and 100.")
        return value


class ProcessQueueSerializer(serializers.Serializer):
    listing_id = serializers.IntegerField(min_value=1)
