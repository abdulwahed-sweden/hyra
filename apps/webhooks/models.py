"""
Webhook event delivery system with exponential backoff retry.

Mirrors HomeQ's production pattern: when a queue is processed or a
tenant is selected, landlord systems receive a webhook notification.
Failed deliveries retry every 5 minutes for up to 7 days.

This demonstrates async architecture thinking for a platform
that integrates with 1000+ property management systems.
"""
import hashlib
import hmac
import json
import logging
from datetime import timedelta

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)

# Retry schedule: 5m, 15m, 1h, 6h, 24h, 48h, 7d
RETRY_DELAYS_MINUTES = [5, 15, 60, 360, 1440, 2880, 10080]
MAX_ATTEMPTS = len(RETRY_DELAYS_MINUTES) + 1


class WebhookEndpoint(models.Model):
    """
    A landlord's registered webhook URL.
    Each landlord can register endpoints to receive events
    about their listings (queue processed, tenant selected, etc.).
    """
    landlord = models.ForeignKey(
        "listings.Landlord",
        on_delete=models.CASCADE,
        related_name="webhook_endpoints",
    )
    url = models.URLField(max_length=500)
    secret = models.CharField(
        max_length=64,
        help_text="HMAC-SHA256 signing secret for payload verification",
    )
    is_active = models.BooleanField(default=True)
    events = models.JSONField(
        default=list,
        help_text="List of event types to receive, e.g. ['queue.processed', 'tenant.selected']",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["landlord", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.landlord.name} → {self.url}"


class WebhookEvent(models.Model):
    """
    An individual webhook delivery attempt.
    Tracks delivery status with retry logic matching HomeQ's pattern:
    retry every 5 minutes, escalating to 7 days before giving up.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
        EXHAUSTED = "exhausted", "Exhausted"

    endpoint = models.ForeignKey(
        WebhookEndpoint,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_retry_at"]),
            models.Index(fields=["endpoint", "event_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} → {self.endpoint.url} ({self.status})"

    def sign_payload(self) -> str:
        """Generate HMAC-SHA256 signature for payload verification."""
        payload_bytes = json.dumps(self.payload, sort_keys=True).encode()
        return hmac.new(
            self.endpoint.secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

    def schedule_retry(self) -> None:
        """
        Schedule next retry with escalating delays.
        Pattern: 5m → 15m → 1h → 6h → 24h → 48h → 7d → exhausted.
        """
        if self.attempts >= MAX_ATTEMPTS:
            self.status = self.Status.EXHAUSTED
            self.save(update_fields=["status"])
            return

        delay_index = min(self.attempts, len(RETRY_DELAYS_MINUTES) - 1)
        delay = timedelta(minutes=RETRY_DELAYS_MINUTES[delay_index])
        self.next_retry_at = timezone.now() + delay
        self.save(update_fields=["next_retry_at"])

    def mark_delivered(self) -> None:
        self.status = self.Status.DELIVERED
        self.delivered_at = timezone.now()
        self.save(update_fields=["status", "delivered_at"])

    def mark_failed(self, error: str) -> None:
        self.attempts += 1
        self.last_attempt_at = timezone.now()
        self.last_error = error
        self.status = self.Status.FAILED
        self.save(update_fields=[
            "attempts", "last_attempt_at", "last_error", "status",
        ])
        self.schedule_retry()


def emit_event(event_type: str, landlord_id: int, payload: dict) -> list:
    """
    Create webhook events for all active endpoints subscribed to this event type.
    Returns list of created WebhookEvent instances.

    Usage:
        emit_event("queue.processed", listing.landlord_id, {
            "listing_id": listing.pk,
            "winner": "Erik Andersson",
            "qualified": 5,
        })
    """
    endpoints = WebhookEndpoint.objects.filter(
        landlord_id=landlord_id,
        is_active=True,
    )

    events = []
    for endpoint in endpoints:
        # Check if endpoint subscribes to this event type
        if endpoint.events and event_type not in endpoint.events:
            continue

        event = WebhookEvent.objects.create(
            endpoint=endpoint,
            event_type=event_type,
            payload={
                "event": event_type,
                "timestamp": timezone.now().isoformat(),
                **payload,
            },
            next_retry_at=timezone.now(),
        )
        events.append(event)
        logger.info("Webhook event created: %s → %s", event_type, endpoint.url)

    return events
