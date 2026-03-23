"""
Listings domain models — the core of Hyra's rental marketplace.

Three models represent the property hierarchy:
Landlord → Listing ← Municipality
"""
from django.db import models


class Landlord(models.Model):
    """Represents a property management company or private landlord."""
    name = models.CharField(max_length=200)
    org_number = models.CharField(
        max_length=20,
        unique=True,
        help_text="Swedish org number format: XXXXXX-XXXX",
    )
    website = models.URLField(blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Municipality(models.Model):
    """Swedish municipality (kommun) for geographic grouping."""
    name = models.CharField(max_length=100)
    county = models.CharField(max_length=100, default="Stockholm")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "municipalities"

    def __str__(self) -> str:
        return self.name


class Listing(models.Model):
    """
    A rental property listing published by a landlord.
    Central model that connects to queue entries, search index, and applications.
    """

    class ListingType(models.TextChoices):
        APARTMENT = "apartment", "Lägenhet"
        ROOM = "room", "Rum"
        HOUSE = "house", "Hus"

    class Status(models.TextChoices):
        ACTIVE = "active", "Aktiv"
        CLOSED = "closed", "Stängd"
        COMING_SOON = "coming_soon", "Kommer snart"

    # Relationships
    landlord = models.ForeignKey(
        Landlord,
        on_delete=models.CASCADE,
        related_name="listings",
    )
    municipality = models.ForeignKey(
        Municipality,
        on_delete=models.SET_NULL,
        null=True,
        related_name="listings",
    )

    # Location
    street_address = models.CharField(max_length=300)
    district = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=10)
    city = models.CharField(max_length=100, default="Stockholm")

    # Property details
    listing_type = models.CharField(
        max_length=20,
        choices=ListingType.choices,
        default=ListingType.APARTMENT,
    )
    rooms = models.PositiveSmallIntegerField()
    size_sqm = models.PositiveIntegerField()
    floor = models.SmallIntegerField(default=1)
    total_floors = models.PositiveSmallIntegerField(default=5)
    has_elevator = models.BooleanField(default=False)
    has_balcony = models.BooleanField(default=False)
    has_parking = models.BooleanField(default=False)
    is_accessible = models.BooleanField(default=False)
    allows_pets = models.BooleanField(default=False)

    # Financial
    rent_sek = models.PositiveIntegerField(help_text="Monthly rent in SEK")
    min_income_multiplier = models.FloatField(
        default=3.0,
        help_text="Applicant income must be at least this multiple of rent",
    )
    max_household_size = models.PositiveSmallIntegerField(default=6)

    # Status & dates
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    available_from = models.DateField()
    application_deadline = models.DateField(null=True, blank=True)
    published_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Content
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["-published_at"]
        indexes = [
            models.Index(fields=["status", "listing_type"]),
            models.Index(fields=["municipality", "rent_sek"]),
            models.Index(fields=["rooms", "size_sqm"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} — {self.rent_sek} kr/mån"

    # applicant_count is provided via .annotate() in querysets, not as a property,
    # because @property conflicts with Django's annotation setattr mechanism
