"""
Tests for webhook event system — delivery tracking, retry logic,
HMAC signing, and integration with queue processing.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.listings.models import Landlord, Listing, Municipality
from apps.queue.models import QueueConfig, QueueEngine, QueueEntry, QueueType
from apps.webhooks.models import (
    MAX_ATTEMPTS,
    WebhookEndpoint,
    WebhookEvent,
    emit_event,
)


class WebhookModelTests(TestCase):
    """Tests for webhook event lifecycle."""

    def setUp(self):
        self.landlord = Landlord.objects.create(
            name="Webhook AB", org_number="556000-7777",
        )
        self.endpoint = WebhookEndpoint.objects.create(
            landlord=self.landlord,
            url="https://hooks.example.com/queue",
            secret="test-secret-key-256",
            events=["queue.processed", "tenant.selected"],
        )

    def test_emit_event_creates_webhook_event(self):
        """emit_event() creates a WebhookEvent for each subscribed endpoint."""
        events = emit_event("queue.processed", self.landlord.pk, {
            "listing_id": 1, "winner": "Test",
        })
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "queue.processed")
        self.assertEqual(events[0].status, WebhookEvent.Status.PENDING)

    def test_emit_event_skips_unsubscribed_types(self):
        """Endpoints only receive events they subscribe to."""
        events = emit_event("listing.created", self.landlord.pk, {})
        self.assertEqual(len(events), 0)

    def test_emit_event_skips_inactive_endpoints(self):
        """Inactive endpoints don't receive events."""
        self.endpoint.is_active = False
        self.endpoint.save(update_fields=["is_active"])
        events = emit_event("queue.processed", self.landlord.pk, {"x": 1})
        self.assertEqual(len(events), 0)

    def test_hmac_signature_is_deterministic(self):
        """Same payload + secret always produces same signature."""
        event = WebhookEvent.objects.create(
            endpoint=self.endpoint,
            event_type="test",
            payload={"key": "value"},
        )
        sig1 = event.sign_payload()
        sig2 = event.sign_payload()
        self.assertEqual(sig1, sig2)
        self.assertEqual(len(sig1), 64)  # SHA-256 hex

    def test_mark_delivered_sets_timestamp(self):
        event = WebhookEvent.objects.create(
            endpoint=self.endpoint, event_type="test", payload={},
        )
        event.mark_delivered()
        event.refresh_from_db()
        self.assertEqual(event.status, WebhookEvent.Status.DELIVERED)
        self.assertIsNotNone(event.delivered_at)

    def test_mark_failed_increments_attempts(self):
        event = WebhookEvent.objects.create(
            endpoint=self.endpoint, event_type="test", payload={},
        )
        event.mark_failed("Connection timeout")
        event.refresh_from_db()
        self.assertEqual(event.attempts, 1)
        self.assertEqual(event.last_error, "Connection timeout")
        self.assertIsNotNone(event.next_retry_at)

    def test_retry_schedule_escalates(self):
        """Each failure increases the delay before next retry."""
        event = WebhookEvent.objects.create(
            endpoint=self.endpoint, event_type="test", payload={},
        )
        retries = []
        for i in range(3):
            event.mark_failed(f"Fail {i}")
            event.refresh_from_db()
            retries.append(event.next_retry_at)

        # Each retry should be further in the future
        self.assertLess(retries[0], retries[1])
        self.assertLess(retries[1], retries[2])

    def test_exhausted_after_max_attempts(self):
        """After MAX_ATTEMPTS failures, status becomes EXHAUSTED."""
        event = WebhookEvent.objects.create(
            endpoint=self.endpoint, event_type="test", payload={},
            attempts=MAX_ATTEMPTS,
        )
        event.schedule_retry()
        event.refresh_from_db()
        self.assertEqual(event.status, WebhookEvent.Status.EXHAUSTED)


class WebhookQueueIntegrationTests(TestCase):
    """Tests that queue processing emits webhook events."""

    def setUp(self):
        self.landlord = Landlord.objects.create(
            name="Integration AB", org_number="556000-8888",
        )
        self.muni = Municipality.objects.create(name="Test")
        self.listing = Listing.objects.create(
            landlord=self.landlord, municipality=self.muni,
            street_address="X", district="Y", postal_code="100 00",
            rooms=2, size_sqm=50, rent_sek=10000, status="active",
            available_from=timezone.localdate() + timedelta(days=14),
            title="Webhook Integration Test",
        )
        QueueConfig.objects.create(
            listing=self.listing, queue_type=QueueType.POINTS,
        )
        self.endpoint = WebhookEndpoint.objects.create(
            landlord=self.landlord,
            url="https://hooks.example.com/events",
            secret="integration-secret",
            events=["queue.processed", "tenant.selected"],
        )

    def test_queue_processing_emits_events(self):
        """Processing a queue emits webhook events to landlord endpoints."""
        QueueEntry.objects.create(
            listing=self.listing,
            applicant_name="Webhook Winner",
            applicant_email="w@test.se",
            monthly_income_sek=40000,
            queue_points=1000,
            bankid_verified=True,
            credit_score=80.0,
        )

        engine = QueueEngine(self.listing)
        engine.process()

        events = WebhookEvent.objects.filter(endpoint__landlord=self.landlord)
        event_types = set(events.values_list("event_type", flat=True))

        self.assertIn("queue.processed", event_types)
        self.assertIn("tenant.selected", event_types)

    def test_queue_processing_works_without_webhooks(self):
        """Queue still works even if no webhook endpoints are registered."""
        self.endpoint.delete()

        QueueEntry.objects.create(
            listing=self.listing,
            applicant_name="No Hooks",
            applicant_email="nh@test.se",
            monthly_income_sek=40000,
            queue_points=500,
            bankid_verified=True,
            credit_score=80.0,
        )

        engine = QueueEngine(self.listing)
        result = engine.process()

        self.assertEqual(result["winner"], "No Hooks")
        self.assertEqual(WebhookEvent.objects.count(), 0)
