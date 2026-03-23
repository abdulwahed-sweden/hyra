"""
Tests for REST API endpoints — verifies response structure,
status codes, filtering, pagination, and error handling.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.listings.models import Landlord, Listing, Municipality
from apps.queue.models import QueueConfig, QueueEntry, QueueType


class APITestMixin:
    """Shared setup for API tests."""

    def setUp(self):
        self.client = APIClient()
        self.landlord = Landlord.objects.create(
            name="API Test AB", org_number="556000-9999",
        )
        self.muni = Municipality.objects.create(name="Solna", county="Stockholm")
        self.listing = Listing.objects.create(
            landlord=self.landlord,
            municipality=self.muni,
            street_address="API-vägen 1",
            district="Hagalund",
            postal_code="171 00",
            rooms=3, size_sqm=70, rent_sek=12000,
            status="active",
            available_from=timezone.localdate() + timedelta(days=14),
            title="API Test Apartment",
        )
        self.config = QueueConfig.objects.create(
            listing=self.listing,
            queue_type=QueueType.POINTS,
        )


class ListingAPITests(APITestMixin, TestCase):
    """Tests for /api/listings/ endpoints."""

    def test_list_returns_200(self):
        resp = self.client.get("/api/listings/")
        self.assertEqual(resp.status_code, 200)

    def test_list_only_active_listings(self):
        Listing.objects.create(
            landlord=self.landlord, municipality=self.muni,
            street_address="Closed 1", district="X", postal_code="100 00",
            rooms=1, size_sqm=30, rent_sek=5000, status="closed",
            available_from=timezone.localdate(), title="Closed",
        )
        resp = self.client.get("/api/listings/")
        titles = [r["title"] for r in resp.data["results"]]
        self.assertIn("API Test Apartment", titles)
        self.assertNotIn("Closed", titles)

    def test_list_includes_applicant_count(self):
        QueueEntry.objects.create(
            listing=self.listing, applicant_name="A",
            applicant_email="a@test.se", monthly_income_sek=40000,
        )
        resp = self.client.get("/api/listings/")
        self.assertEqual(resp.data["results"][0]["applicant_count"], 1)

    def test_detail_returns_nested_landlord(self):
        resp = self.client.get(f"/api/listings/{self.listing.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["landlord"]["name"], "API Test AB")

    def test_stats_returns_aggregates(self):
        resp = self.client.get("/api/listings/stats/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("total", resp.data)
        self.assertIn("avg_rent", resp.data)
        self.assertIn("by_type", resp.data)
        self.assertIn("by_district", resp.data)

    def test_similar_excludes_self(self):
        resp = self.client.get(f"/api/listings/{self.listing.pk}/similar/")
        self.assertEqual(resp.status_code, 200)
        ids = [r["id"] for r in resp.data]
        self.assertNotIn(self.listing.pk, ids)

    def test_filter_by_rent_range(self):
        resp = self.client.get("/api/listings/?min_rent=10000&max_rent=15000")
        self.assertEqual(resp.status_code, 200)
        for r in resp.data["results"]:
            self.assertGreaterEqual(r["rent_sek"], 10000)
            self.assertLessEqual(r["rent_sek"], 15000)

    def test_search_by_title(self):
        resp = self.client.get("/api/listings/?search=API+Test")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data["count"], 1)

    def test_ordering_by_rent(self):
        Listing.objects.create(
            landlord=self.landlord, municipality=self.muni,
            street_address="Cheap 1", district="X", postal_code="100 00",
            rooms=1, size_sqm=25, rent_sek=5000, status="active",
            available_from=timezone.localdate(), title="Cheap",
        )
        resp = self.client.get("/api/listings/?ordering=rent_sek")
        rents = [r["rent_sek"] for r in resp.data["results"]]
        self.assertEqual(rents, sorted(rents))

    def test_nonexistent_listing_returns_404(self):
        resp = self.client.get("/api/listings/99999/")
        self.assertEqual(resp.status_code, 404)

    def test_pagination_structure(self):
        resp = self.client.get("/api/listings/?page=1")
        self.assertIn("count", resp.data)
        self.assertIn("results", resp.data)
        self.assertIn("next", resp.data)
        self.assertIn("previous", resp.data)


class QueueAPITests(APITestMixin, TestCase):
    """Tests for /api/queue/ endpoints."""

    def setUp(self):
        super().setUp()
        self.entry = QueueEntry.objects.create(
            listing=self.listing,
            applicant_name="Queue Test",
            applicant_email="queue@test.se",
            monthly_income_sek=40000,
            queue_points=2000,
            bankid_verified=True,
            credit_score=80.0,
        )

    def test_process_returns_summary(self):
        resp = self.client.post(
            "/api/queue/entries/process/",
            {"listing_id": self.listing.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("winner", resp.data)
        self.assertIn("qualified", resp.data)
        self.assertIn("queue_type", resp.data)

    def test_process_nonexistent_listing_returns_404(self):
        resp = self.client.post(
            "/api/queue/entries/process/",
            {"listing_id": 99999},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_process_missing_listing_id_returns_400(self):
        resp = self.client.post(
            "/api/queue/entries/process/", {}, format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_leaderboard_returns_ranked_entries(self):
        # Process first to generate rankings
        self.client.post(
            "/api/queue/entries/process/",
            {"listing_id": self.listing.pk},
            format="json",
        )
        resp = self.client.get(
            f"/api/queue/entries/leaderboard/?listing={self.listing.pk}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("entries", resp.data)
        self.assertIn("winner", resp.data)

    def test_leaderboard_missing_param_returns_400(self):
        resp = self.client.get("/api/queue/entries/leaderboard/")
        self.assertEqual(resp.status_code, 400)

    def test_leaderboard_invalid_param_returns_400(self):
        resp = self.client.get("/api/queue/entries/leaderboard/?listing=abc")
        self.assertEqual(resp.status_code, 400)

    def test_stats_returns_aggregates(self):
        resp = self.client.get("/api/queue/entries/stats/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("total", resp.data)
        self.assertIn("by_status", resp.data)

    def test_entry_validation_rejects_negative_income(self):
        resp = self.client.post("/api/queue/entries/", {
            "listing": self.listing.pk,
            "applicant_name": "Bad",
            "applicant_email": "bad@test.se",
            "monthly_income_sek": -1000,
            "credit_score": 50,
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_entry_validation_rejects_invalid_credit_score(self):
        resp = self.client.post("/api/queue/entries/", {
            "listing": self.listing.pk,
            "applicant_name": "Bad",
            "applicant_email": "bad2@test.se",
            "monthly_income_sek": 30000,
            "credit_score": 150,
        }, format="json")
        self.assertEqual(resp.status_code, 400)


class SearchAPITests(APITestMixin, TestCase):
    """Tests for /api/search/ endpoint (Postgres fallback)."""

    def test_search_returns_200(self):
        resp = self.client.get("/api/search/?q=Hagalund")
        self.assertEqual(resp.status_code, 200)

    def test_search_includes_engine_field(self):
        resp = self.client.get("/api/search/?q=test")
        self.assertIn("engine", resp.data)
        # Without ES running, should be postgres_fallback
        self.assertEqual(resp.data["engine"], "postgres_fallback")

    def test_search_includes_facets(self):
        resp = self.client.get("/api/search/?q=test")
        self.assertIn("facets", resp.data)
        self.assertIn("by_district", resp.data["facets"])

    def test_search_includes_total_pages(self):
        resp = self.client.get("/api/search/?q=test")
        self.assertIn("total_pages", resp.data)

    def test_search_filters_by_rent(self):
        resp = self.client.get("/api/search/?q=&max_rent=15000")
        self.assertEqual(resp.status_code, 200)

    def test_search_invalid_page_defaults_to_1(self):
        resp = self.client.get("/api/search/?q=test&page=abc")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["page"], 1)

    def test_empty_search_returns_all_active(self):
        resp = self.client.get("/api/search/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data["count"], 1)


class HealthCheckTests(TestCase):
    """Tests for /health/ endpoint."""

    def test_health_returns_200(self):
        resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})
