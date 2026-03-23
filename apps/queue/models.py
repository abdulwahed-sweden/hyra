"""
Queue engine — the centerpiece of Hyra.

Models the full lifecycle of a rental application queue:
config → entry → eligibility check → ranking → selection.

QueueEngine is a pure Python class with explicit, testable business logic.
No signals, no magic — every step is auditable.
"""
import random

from django.db import models, transaction
from django.utils import timezone


class QueueType(models.TextChoices):
    POINTS = "points", "Köpoäng"
    FIRST_COME = "first_come", "Först till kvarn"
    LOTTERY = "lottery", "Lottning"


class QueueConfig(models.Model):
    """
    Per-listing queue configuration.
    Controls which ranking algorithm and eligibility rules apply.
    """
    listing = models.OneToOneField(
        "listings.Listing",
        on_delete=models.CASCADE,
        related_name="queue_config",
    )
    queue_type = models.CharField(
        max_length=20,
        choices=QueueType.choices,
        default=QueueType.POINTS,
    )
    require_bankid = models.BooleanField(default=True)
    require_no_debt = models.BooleanField(default=True)
    min_credit_score = models.FloatField(default=60.0)
    min_queue_points = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kökonfiguration"
        verbose_name_plural = "Kökonfigurationer"

    def __str__(self) -> str:
        return f"Queue config for {self.listing_id}: {self.queue_type}"


class QueueEntry(models.Model):
    """
    A single applicant's position in a listing's queue.
    Stores a denormalized snapshot of applicant data at time of application.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Väntande"
        QUALIFIED = "qualified", "Kvalificerad"
        DISQUALIFIED = "disqualified", "Diskvalificerad"
        SELECTED = "selected", "Utvald"
        REJECTED = "rejected", "Avvisad"
        WITHDRAWN = "withdrawn", "Återkallad"

    listing = models.ForeignKey(
        "listings.Listing",
        on_delete=models.CASCADE,
        related_name="queue_entries",
    )

    # Applicant snapshot (denormalized — captured at application time)
    applicant_name = models.CharField(max_length=200)
    applicant_email = models.EmailField()
    monthly_income_sek = models.PositiveIntegerField()
    household_size = models.PositiveSmallIntegerField(default=1)
    queue_points = models.PositiveIntegerField(default=0)
    bankid_verified = models.BooleanField(default=False)
    credit_score = models.FloatField(default=50.0)
    has_debt_records = models.BooleanField(default=False)
    preferred_districts = models.CharField(max_length=500, blank=True)

    # Queue state
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    disqualification_reason = models.CharField(max_length=300, blank=True)
    rank_score = models.FloatField(null=True, blank=True)
    rank_position = models.PositiveIntegerField(null=True, blank=True)
    applied_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-queue_points", "applied_at"]
        unique_together = [["listing", "applicant_email"]]
        indexes = [
            models.Index(fields=["listing", "status"]),
            models.Index(fields=["queue_points"]),
        ]
        verbose_name = "Köplats"
        verbose_name_plural = "Köplatser"

    def __str__(self) -> str:
        return f"{self.applicant_name} → {self.listing_id} ({self.status})"


class QueueEngine:
    """
    Processes a listing's applicant queue in a single atomic transaction.
    Separates eligibility checking from ranking — each step is independently testable.

    Usage:
        engine = QueueEngine(listing)
        result = engine.process()
    """

    def __init__(self, listing):
        self.listing = listing
        self.config = getattr(listing, "queue_config", None)

    def process(self) -> dict:
        """
        Run the full queue processing pipeline:
        1. Lock entries to prevent concurrent modification
        2. Check eligibility for each pending entry
        3. Rank qualified entries by the configured algorithm
        4. Select the top-ranked applicant as winner
        """
        if not self.config:
            # Auto-create a default config if none exists
            self.config = QueueConfig.objects.create(listing=self.listing)

        with transaction.atomic():
            entries = list(
                QueueEntry.objects.select_for_update()
                .filter(listing=self.listing, status=QueueEntry.Status.PENDING)
            )

            now = timezone.now()
            qualified = []
            disqualified = 0

            for entry in entries:
                reason = self._check_eligibility(entry)
                if reason:
                    entry.status = QueueEntry.Status.DISQUALIFIED
                    entry.disqualification_reason = reason
                    entry.processed_at = now
                    entry.save(update_fields=[
                        "status", "disqualification_reason", "processed_at",
                    ])
                    disqualified += 1
                else:
                    entry.status = QueueEntry.Status.QUALIFIED
                    entry.processed_at = now
                    entry.save(update_fields=["status", "processed_at"])
                    qualified.append(entry)

            winner = None
            winner_score = None

            if qualified:
                ranked = self._rank(qualified)
                for position, entry in enumerate(ranked, start=1):
                    entry.rank_position = position
                    if position == 1:
                        entry.status = QueueEntry.Status.SELECTED
                        winner = entry.applicant_name
                        winner_score = entry.rank_score
                    else:
                        entry.status = QueueEntry.Status.REJECTED
                    entry.save(update_fields=[
                        "status", "rank_score", "rank_position",
                    ])

        return {
            "listing_id": self.listing.pk,
            "queue_type": self.config.queue_type,
            "total": len(entries),
            "qualified": len(qualified),
            "disqualified": disqualified,
            "winner": winner,
            "winner_score": winner_score,
        }

    def _check_eligibility(self, entry: QueueEntry) -> str:
        """
        Returns a disqualification reason string, or empty string if eligible.
        Rules are applied in priority order — first failure wins.
        """
        listing = self.listing
        config = self.config

        # 1. Debt records — automatic disqualification
        if entry.has_debt_records:
            return "Kronofogden debt records"

        # 2. Income requirement
        required_income = listing.rent_sek * listing.min_income_multiplier
        if entry.monthly_income_sek < required_income:
            return (
                f"Insufficient income: {entry.monthly_income_sek} SEK "
                f"< {int(required_income)} SEK"
            )

        # 3. Household size cap
        if entry.household_size > listing.max_household_size:
            return (
                f"Household size {entry.household_size} "
                f"> max {listing.max_household_size}"
            )

        # 4. BankID verification
        if config.require_bankid and not entry.bankid_verified:
            return "BankID verification required"

        # 5. Credit score threshold
        if entry.credit_score < config.min_credit_score:
            return (
                f"Credit score {entry.credit_score} "
                f"< minimum {config.min_credit_score}"
            )

        # 6. Minimum queue points
        if config.min_queue_points and entry.queue_points < config.min_queue_points:
            return (
                f"Queue points {entry.queue_points} "
                f"< minimum {config.min_queue_points}"
            )

        return ""

    def _rank(self, entries: list[QueueEntry]) -> list[QueueEntry]:
        """Dispatch to the correct ranking method based on queue_type."""
        rankers = {
            QueueType.POINTS: self._rank_by_points,
            QueueType.FIRST_COME: self._rank_by_first_come,
            QueueType.LOTTERY: self._rank_by_lottery,
        }
        ranker = rankers[self.config.queue_type]
        return ranker(entries)

    def _rank_by_points(self, entries: list[QueueEntry]) -> list[QueueEntry]:
        """Sort by accumulated queue points — highest first."""
        entries.sort(key=lambda e: e.queue_points, reverse=True)
        max_points = entries[0].queue_points if entries else 1
        # Avoid division by zero
        max_points = max_points or 1
        for entry in entries:
            entry.rank_score = (entry.queue_points / max_points) * 100
        return entries

    def _rank_by_first_come(self, entries: list[QueueEntry]) -> list[QueueEntry]:
        """Sort by application timestamp — earliest first."""
        entries.sort(key=lambda e: e.applied_at)
        total = len(entries)
        for position, entry in enumerate(entries):
            entry.rank_score = ((total - position) / total) * 100
        return entries

    def _rank_by_lottery(self, entries: list[QueueEntry]) -> list[QueueEntry]:
        """
        Reproducible random shuffle seeded by listing PK.
        Same listing always produces the same lottery order — auditable.
        """
        rng = random.Random(self.listing.pk)
        rng.shuffle(entries)
        total = len(entries)
        for position, entry in enumerate(entries):
            entry.rank_score = ((total - position) / total) * 100
        return entries
