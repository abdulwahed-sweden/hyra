"""API views for queue management — process, leaderboard, and stats."""
from django.db.models import Avg, Count

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.listings.models import Listing

from .models import QueueEngine, QueueEntry
from .serializers import ProcessQueueSerializer, QueueEntrySerializer


class QueueViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for queue entries plus processing, leaderboard, and stats actions.
    """
    queryset = QueueEntry.objects.select_related("listing")
    serializer_class = QueueEntrySerializer
    filterset_fields = ["listing", "status"]
    ordering_fields = ["queue_points", "rank_position", "applied_at"]
    ordering = ["id"]

    @action(detail=False, methods=["post"])
    def process(self, request):
        """
        Run the queue engine for a given listing.
        Expects: {"listing_id": <int>}
        Returns processing summary with winner info.
        """
        serializer = ProcessQueueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        listing_id = serializer.validated_data["listing_id"]
        try:
            listing = Listing.objects.get(pk=listing_id)
        except Listing.DoesNotExist:
            return Response(
                {"error": f"Listing {listing_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        engine = QueueEngine(listing)
        result = engine.process()
        return Response(result)

    @action(detail=False, methods=["get"])
    def leaderboard(self, request):
        """
        Ranked entries for a listing.
        Query param: ?listing=<id>
        Returns ranked entries with winner highlighted.
        """
        listing_id = request.query_params.get("listing")
        if not listing_id:
            return Response(
                {"error": "listing query parameter required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # [H8] Validate listing_id is a valid integer
        try:
            listing_id = int(listing_id)
        except (ValueError, TypeError):
            return Response(
                {"error": "listing must be a valid integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        entries = (
            QueueEntry.objects
            .filter(listing_id=listing_id, rank_position__isnull=False)
            .order_by("rank_position")
        )
        serializer = QueueEntrySerializer(entries, many=True)

        winner = entries.filter(status=QueueEntry.Status.SELECTED).first()
        return Response({
            "listing_id": listing_id,
            "entries": serializer.data,
            "winner": winner.applicant_name if winner else None,
        })

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Aggregate queue statistics across all entries."""
        qs = QueueEntry.objects.all()

        by_status = list(
            qs.values("status")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        agg = qs.aggregate(
            total=Count("id"),
            avg_points=Avg("queue_points"),
            avg_credit_score=Avg("credit_score"),
        )

        return Response({
            **agg,
            "by_status": by_status,
        })
