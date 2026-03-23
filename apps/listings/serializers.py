"""Serializers for the listings API."""
from rest_framework import serializers

from .models import Landlord, Listing, Municipality


class LandlordSerializer(serializers.ModelSerializer):
    class Meta:
        model = Landlord
        fields = ["id", "name", "org_number", "website", "is_verified"]


class MunicipalitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Municipality
        fields = ["id", "name", "county"]


class ListingListSerializer(serializers.ModelSerializer):
    """Compact serializer for list views — includes computed applicant_count."""
    landlord_name = serializers.CharField(source="landlord.name", read_only=True)
    municipality_name = serializers.CharField(
        source="municipality.name", read_only=True, default=None,
    )
    applicant_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Listing
        fields = [
            "id", "title", "street_address", "district", "postal_code", "city",
            "listing_type", "rooms", "size_sqm", "rent_sek", "status",
            "available_from", "has_balcony", "has_parking", "allows_pets",
            "has_elevator", "is_accessible",
            "landlord_name", "municipality_name", "applicant_count",
            "published_at",
        ]


class ListingDetailSerializer(serializers.ModelSerializer):
    """Full serializer for detail views — all fields plus nested relations."""
    landlord = LandlordSerializer(read_only=True)
    municipality = MunicipalitySerializer(read_only=True)
    applicant_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Listing
        fields = "__all__"
