"""API views for listings — read-only viewset with stats and similar actions."""
from django.db.models import Avg, Count, Max, Min

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .filters import ListingFilter
from .models import Listing
from .serializers import ListingDetailSerializer, ListingListSerializer


class ListingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API for rental listings.
    Supports filtering, search, ordering, and aggregate stats.
    """
    filterset_class = ListingFilter
    search_fields = ["title", "street_address", "district", "description"]
    ordering_fields = ["rent_sek", "rooms", "size_sqm", "published_at", "applicant_count"]

    def get_queryset(self):
        return (
            Listing.objects
            .select_related("landlord", "municipality")
            .annotate(applicant_count=Count("queue_entries"))
            .filter(status=Listing.Status.ACTIVE)
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ListingDetailSerializer
        return ListingListSerializer

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Aggregate statistics across all active listings."""
        # Use a clean queryset without the applicant_count annotation
        # to avoid JOIN-inflated counts in values().annotate() calls
        qs = Listing.objects.filter(status=Listing.Status.ACTIVE)
        agg = qs.aggregate(
            total=Count("id"),
            avg_rent=Avg("rent_sek"),
            min_rent=Min("rent_sek"),
            max_rent=Max("rent_sek"),
            avg_size=Avg("size_sqm"),
        )

        by_type = list(
            qs.values("listing_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        by_district = list(
            qs.values("district")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        return Response({
            **agg,
            "by_type": by_type,
            "by_district": by_district,
        })

    @action(detail=True, methods=["get"])
    def similar(self, request, pk=None):
        """Find similar listings in the same municipality with same room count."""
        listing = self.get_object()
        similar_qs = (
            self.get_queryset()
            .filter(municipality=listing.municipality, rooms=listing.rooms)
            .exclude(pk=listing.pk)[:4]
        )
        serializer = ListingListSerializer(similar_qs, many=True)
        return Response(serializer.data)
