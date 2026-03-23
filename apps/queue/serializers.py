"""Serializers for the queue API."""
from rest_framework import serializers

from .models import QueueConfig, QueueEntry


class QueueConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = QueueConfig
        fields = "__all__"


class QueueEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = QueueEntry
        fields = "__all__"
        read_only_fields = [
            "status", "disqualification_reason",
            "rank_score", "rank_position", "processed_at",
        ]


class ProcessQueueSerializer(serializers.Serializer):
    listing_id = serializers.IntegerField()
