"""Filter definitions for listing queries."""
import django_filters

from .models import Listing


class ListingFilter(django_filters.FilterSet):
    """Supports range filters on rent, rooms, and size plus exact district match."""
    min_rent = django_filters.NumberFilter(field_name="rent_sek", lookup_expr="gte")
    max_rent = django_filters.NumberFilter(field_name="rent_sek", lookup_expr="lte")
    min_rooms = django_filters.NumberFilter(field_name="rooms", lookup_expr="gte")
    max_rooms = django_filters.NumberFilter(field_name="rooms", lookup_expr="lte")
    min_size = django_filters.NumberFilter(field_name="size_sqm", lookup_expr="gte")
    max_size = django_filters.NumberFilter(field_name="size_sqm", lookup_expr="lte")
    district = django_filters.CharFilter(lookup_expr="icontains")
    listing_type = django_filters.ChoiceFilter(choices=Listing.ListingType.choices)
    has_balcony = django_filters.BooleanFilter()
    has_parking = django_filters.BooleanFilter()
    allows_pets = django_filters.BooleanFilter()
    has_elevator = django_filters.BooleanFilter()

    class Meta:
        model = Listing
        fields = [
            "min_rent", "max_rent", "min_rooms", "max_rooms",
            "min_size", "max_size", "district", "listing_type",
            "has_balcony", "has_parking", "allows_pets", "has_elevator",
        ]
