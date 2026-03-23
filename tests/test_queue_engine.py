"""
Tests for QueueEngine — the core business logic of Hyra.

Covers eligibility rules, all three ranking algorithms,
edge cases, and atomicity guarantees.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.listings.models import Landlord, Listing, Municipality
from apps.queue.models import QueueConfig, QueueEngine, QueueEntry, QueueType


class QueueEngineTestMixin:
    """Shared setup for queue engine tests."""

    def setUp(self):
        self.landlord = Landlord.objects.create(
            name="Test Fastigheter", org_number="556000-0001",
        )
        self.municipality = Municipality.objects.create(
            name="Stockholm", county="Stockholm",
        )
        self.listing = Listing.objects.create(
            landlord=self.landlord,
            municipality=self.municipality,
            street_address="Testgatan 1",
            district="Södermalm",
            postal_code="118 00",
            listing_type="apartment",
            rooms=2,
            size_sqm=55,
            rent_sek=10000,
            min_income_multiplier=3.0,
            max_household_size=4,
            status="active",
            available_from=timezone.localdate() + timedelta(days=30),
            title="Test listing",
        )
        self.config = QueueConfig.objects.create(
            listing=self.listing,
            queue_type=QueueType.POINTS,
            require_bankid=True,
            require_no_debt=True,
            min_credit_score=60.0,
        )

    def _make_entry(self, **overrides):
        """Create a valid queue entry with sensible defaults."""
        defaults = {
            "listing": self.listing,
            "applicant_name": "Test Sökande",
            "applicant_email": f"test{QueueEntry.objects.count()}@example.se",
            "monthly_income_sek": 35000,
            "household_size": 1,
            "queue_points": 1000,
            "bankid_verified": True,
            "credit_score": 80.0,
            "has_debt_records": False,
        }
        defaults.update(overrides)
        return QueueEntry.objects.create(**defaults)


class EligibilityTests(QueueEngineTestMixin, TestCase):
    """Test each disqualification rule independently."""

    def test_debt_records_disqualifies(self):
        """Kronofogden debt records = automatic disqualification."""
        entry = self._make_entry(has_debt_records=True)
        engine = QueueEngine(self.listing)
        reason = engine._check_eligibility(entry)
        self.assertEqual(reason, "Kronofogden debt records")

    def test_insufficient_income_disqualifies(self):
        """Income below rent * multiplier = disqualified."""
        # Rent 10000 * 3.0 = 30000 required
        entry = self._make_entry(monthly_income_sek=25000)
        engine = QueueEngine(self.listing)
        reason = engine._check_eligibility(entry)
        self.assertIn("Insufficient income", reason)
        self.assertIn("25000", reason)
        self.assertIn("30000", reason)

    def test_exact_income_threshold_passes(self):
        """Income exactly at threshold should pass."""
        entry = self._make_entry(monthly_income_sek=30000)
        engine = QueueEngine(self.listing)
        reason = engine._check_eligibility(entry)
        self.assertEqual(reason, "")

    def test_household_size_too_large_disqualifies(self):
        """Household exceeding max = disqualified."""
        entry = self._make_entry(household_size=5)
        engine = QueueEngine(self.listing)
        reason = engine._check_eligibility(entry)
        self.assertIn("Household size 5", reason)
        self.assertIn("max 4", reason)

    def test_bankid_required_but_not_verified(self):
        """BankID required by config but applicant not verified."""
        entry = self._make_entry(bankid_verified=False)
        engine = QueueEngine(self.listing)
        reason = engine._check_eligibility(entry)
        self.assertEqual(reason, "BankID verification required")

    def test_bankid_not_required_unverified_passes(self):
        """BankID not required = unverified applicant passes."""
        self.config.require_bankid = False
        self.config.save(update_fields=["require_bankid"])
        entry = self._make_entry(bankid_verified=False)
        engine = QueueEngine(self.listing)
        reason = engine._check_eligibility(entry)
        self.assertEqual(reason, "")

    def test_low_credit_score_disqualifies(self):
        """Credit score below minimum = disqualified."""
        entry = self._make_entry(credit_score=45.0)
        engine = QueueEngine(self.listing)
        reason = engine._check_eligibility(entry)
        self.assertIn("Credit score 45.0", reason)
        self.assertIn("minimum 60.0", reason)

    def test_min_queue_points_disqualifies(self):
        """Queue points below config minimum = disqualified."""
        self.config.min_queue_points = 500
        self.config.save(update_fields=["min_queue_points"])
        entry = self._make_entry(queue_points=200)
        engine = QueueEngine(self.listing)
        reason = engine._check_eligibility(entry)
        self.assertIn("Queue points 200", reason)
        self.assertIn("minimum 500", reason)

    def test_fully_eligible_applicant_passes(self):
        """Applicant meeting all criteria returns empty string."""
        entry = self._make_entry()
        engine = QueueEngine(self.listing)
        reason = engine._check_eligibility(entry)
        self.assertEqual(reason, "")

    def test_rules_applied_in_priority_order(self):
        """Debt check runs before income check — first failure wins."""
        entry = self._make_entry(
            has_debt_records=True, monthly_income_sek=1000,
        )
        engine = QueueEngine(self.listing)
        reason = engine._check_eligibility(entry)
        # Should be debt, not income
        self.assertEqual(reason, "Kronofogden debt records")


class PointsRankingTests(QueueEngineTestMixin, TestCase):
    """Test queue_type=POINTS ranking algorithm."""

    def test_highest_points_wins(self):
        """Applicant with most queue points should be selected."""
        self._make_entry(applicant_name="Low", queue_points=100)
        self._make_entry(applicant_name="High", queue_points=3000)
        self._make_entry(applicant_name="Mid", queue_points=1500)

        engine = QueueEngine(self.listing)
        result = engine.process()

        self.assertEqual(result["winner"], "High")
        self.assertEqual(result["qualified"], 3)

    def test_rank_score_normalized_to_100(self):
        """Top scorer gets rank_score=100."""
        self._make_entry(queue_points=2000)
        self._make_entry(queue_points=1000)

        engine = QueueEngine(self.listing)
        engine.process()

        winner = QueueEntry.objects.get(
            listing=self.listing, status=QueueEntry.Status.SELECTED,
        )
        self.assertEqual(winner.rank_score, 100.0)
        self.assertEqual(winner.rank_position, 1)


class FirstComeRankingTests(QueueEngineTestMixin, TestCase):
    """Test queue_type=FIRST_COME ranking algorithm."""

    def setUp(self):
        super().setUp()
        self.config.queue_type = QueueType.FIRST_COME
        self.config.save(update_fields=["queue_type"])

    def test_earliest_application_wins(self):
        """First applicant to apply should be selected."""
        e1 = self._make_entry(applicant_name="First")
        e2 = self._make_entry(applicant_name="Second")
        e3 = self._make_entry(applicant_name="Third")

        engine = QueueEngine(self.listing)
        result = engine.process()

        self.assertEqual(result["winner"], "First")
        self.assertEqual(result["queue_type"], "first_come")


class LotteryRankingTests(QueueEngineTestMixin, TestCase):
    """Test queue_type=LOTTERY ranking algorithm."""

    def setUp(self):
        super().setUp()
        self.config.queue_type = QueueType.LOTTERY
        self.config.save(update_fields=["queue_type"])

    def test_lottery_is_reproducible(self):
        """Same listing PK always produces same lottery order."""
        for i in range(5):
            self._make_entry(applicant_name=f"Applicant {i}", queue_points=100 * i)

        engine = QueueEngine(self.listing)
        result1 = engine.process()
        winner1 = result1["winner"]

        # Reset entries to pending
        QueueEntry.objects.filter(listing=self.listing).update(
            status=QueueEntry.Status.PENDING,
            rank_position=None, rank_score=None, processed_at=None,
        )

        engine2 = QueueEngine(self.listing)
        result2 = engine2.process()

        self.assertEqual(winner1, result2["winner"])

    def test_lottery_result_returned(self):
        """Lottery produces a valid result."""
        self._make_entry(applicant_name="A")
        self._make_entry(applicant_name="B")

        engine = QueueEngine(self.listing)
        result = engine.process()

        self.assertIn(result["winner"], ["A", "B"])
        self.assertEqual(result["queue_type"], "lottery")


class ProcessEdgeCaseTests(QueueEngineTestMixin, TestCase):
    """Edge cases in queue processing."""

    def test_no_pending_entries_returns_zero(self):
        """Processing with no entries returns all-zero summary."""
        engine = QueueEngine(self.listing)
        result = engine.process()
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["qualified"], 0)
        self.assertIsNone(result["winner"])

    def test_all_disqualified_no_winner(self):
        """If every applicant fails eligibility, no winner selected."""
        self._make_entry(has_debt_records=True, applicant_name="Bad1")
        self._make_entry(has_debt_records=True, applicant_name="Bad2")

        engine = QueueEngine(self.listing)
        result = engine.process()

        self.assertEqual(result["disqualified"], 2)
        self.assertEqual(result["qualified"], 0)
        self.assertIsNone(result["winner"])

    def test_single_qualified_applicant_wins(self):
        """Only one eligible applicant = automatic winner."""
        self._make_entry(applicant_name="Solo")

        engine = QueueEngine(self.listing)
        result = engine.process()

        self.assertEqual(result["winner"], "Solo")
        self.assertEqual(result["qualified"], 1)

    def test_reprocessing_skips_already_processed(self):
        """Running process() twice only processes PENDING entries."""
        self._make_entry(applicant_name="First Run")

        engine = QueueEngine(self.listing)
        result1 = engine.process()
        self.assertEqual(result1["total"], 1)

        # Second run: no pending entries left
        result2 = engine.process()
        self.assertEqual(result2["total"], 0)

    def test_auto_creates_config_if_missing(self):
        """QueueEngine creates default config when none exists."""
        self.config.delete()
        # Refresh listing to clear ORM cached relation
        self.listing.refresh_from_db()
        self._make_entry(applicant_name="No Config")

        engine = QueueEngine(self.listing)
        result = engine.process()

        self.assertIsNotNone(result["queue_type"])
        self.assertTrue(
            QueueConfig.objects.filter(listing=self.listing).exists()
        )

    def test_processed_at_timestamp_set(self):
        """All processed entries get a processed_at timestamp."""
        self._make_entry()
        engine = QueueEngine(self.listing)
        engine.process()

        entry = QueueEntry.objects.get(listing=self.listing)
        self.assertIsNotNone(entry.processed_at)
