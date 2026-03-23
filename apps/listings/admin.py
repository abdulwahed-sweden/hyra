"""Admin configuration for listings."""
from django.contrib import admin

from .models import Landlord, Listing, Municipality


@admin.register(Landlord)
class LandlordAdmin(admin.ModelAdmin):
    list_display = ["name", "org_number", "is_verified", "created_at"]
    list_filter = ["is_verified"]
    search_fields = ["name", "org_number"]


@admin.register(Municipality)
class MunicipalityAdmin(admin.ModelAdmin):
    list_display = ["name", "county"]
    list_filter = ["county"]


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = [
        "title", "landlord", "district", "rooms", "rent_sek",
        "status", "listing_type", "published_at",
    ]
    list_filter = ["status", "listing_type", "municipality"]
    search_fields = ["title", "street_address", "district"]
    raw_id_fields = ["landlord", "municipality"]
