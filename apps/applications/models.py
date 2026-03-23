"""
Applications domain — tracks applicant submissions linked to listings.
"""
from django.db import models


class Application(models.Model):
    """
    An applicant's formal submission for a listing.
    Represents the user-facing side of the queue entry.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Utkast"
        SUBMITTED = "submitted", "Inskickad"
        UNDER_REVIEW = "under_review", "Under granskning"
        APPROVED = "approved", "Godkänd"
        REJECTED = "rejected", "Avvisad"
        WITHDRAWN = "withdrawn", "Återkallad"

    listing = models.ForeignKey(
        "listings.Listing",
        on_delete=models.CASCADE,
        related_name="applications",
    )
    applicant_name = models.CharField(max_length=200)
    applicant_email = models.EmailField()
    phone_number = models.CharField(max_length=20, blank=True)
    message = models.TextField(
        blank=True,
        help_text="Personal message to the landlord",
    )
    monthly_income_sek = models.PositiveIntegerField()
    household_size = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        unique_together = [["listing", "applicant_email"]]
        verbose_name = "Ansökan"
        verbose_name_plural = "Ansökningar"

    def __str__(self) -> str:
        return f"{self.applicant_name} → {self.listing_id}"
