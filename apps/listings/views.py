"""API views for listings — read-only viewset with stats and similar actions."""
import json
import logging

from django.core.cache import cache
from django.db.models import Avg, Count, Max, Min

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .filters import ListingFilter
from .models import Listing
from .serializers import ListingDetailSerializer, ListingListSerializer

logger = logging.getLogger(__name__)

# Cache TTL for stats — high-read endpoint, data changes infrequently
STATS_CACHE_TTL = 60  # seconds


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
        """
        Aggregate statistics across all active listings.

        Redis-cached for 60s — this is the highest-traffic endpoint
        (called by dashboard, landing page, and analytics on every load).
        In production with 1000+ landlords, this prevents DB pressure
        on an endpoint whose data changes infrequently.
        """
        cached = cache.get("listing_stats")
        if cached:
            return Response(json.loads(cached))

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

        result = {
            **agg,
            "by_type": by_type,
            "by_district": by_district,
        }

        try:
            cache.set("listing_stats", json.dumps(result), STATS_CACHE_TTL)
        except Exception:
            pass  # Cache is optional — degrade gracefully

        return Response(result)

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
