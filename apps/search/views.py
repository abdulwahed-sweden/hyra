"""
Search views — Elasticsearch with automatic Postgres fallback.

The search always returns results: if ES is unavailable, a Postgres
ILIKE query transparently takes over. The response includes an 'engine'
field so the client knows which backend served the results.
"""
import logging

from django.db.models import Avg, Count, Max, Min, Q

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError as ESConnectionError
from elastic_transport import ConnectionError as TransportConnectionError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.listings.models import Listing
from apps.listings.serializers import ListingListSerializer

from decouple import config as env_config

logger = logging.getLogger(__name__)

# [H10] Module-level ES client singleton — avoids per-request connection leak
ES_INDEX = "hyra_listings"
_es_client = None


def _get_es_client():
    """Lazy singleton for Elasticsearch client to avoid connection leak."""
    global _es_client
    if _es_client is None:
        es_url = env_config("ELASTICSEARCH_URL", default="http://localhost:9200")
        _es_client = Elasticsearch([es_url])
    return _es_client


class ListingSearchView(APIView):
    """
    GET /api/search/?q=södermalm&max_rent=12000&rooms=2

    Tries Elasticsearch first, falls back to Postgres on any failure.
    """

    def get(self, request):
        query = request.query_params.get("q", "")
        max_rent = request.query_params.get("max_rent")
        rooms = request.query_params.get("rooms")
        has_balcony = request.query_params.get("has_balcony")
        allows_pets = request.query_params.get("allows_pets")
        # [M10] Validate page param — default to 1 on invalid input
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (ValueError, TypeError):
            page = 1
        page_size = 12

        try:
            return self._elasticsearch_search(
                query, max_rent, rooms, has_balcony, allows_pets, page, page_size,
            )
        except (ESConnectionError, TransportConnectionError, ConnectionError, Exception) as exc:
            logger.warning("Elasticsearch unavailable, falling back to Postgres: %s", exc)
            return self._postgres_fallback(
                query, max_rent, rooms, has_balcony, allows_pets, page, page_size,
            )

    def _elasticsearch_search(self, query, max_rent, rooms, has_balcony,
                               allows_pets, page, page_size):
        """Full-text search via Elasticsearch with aggregations."""
        es = _get_es_client()

        body = {"query": {"bool": {"must": [], "filter": []}}}

        if query:
            body["query"]["bool"]["must"].append({
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "description", "district^2",
                               "municipality^2", "street_address"],
                    "fuzziness": "AUTO",
                }
            })
        else:
            body["query"]["bool"]["must"].append({"match_all": {}})

        body["query"]["bool"]["filter"].append(
            {"term": {"status": "active"}}
        )

        if max_rent:
            body["query"]["bool"]["filter"].append(
                {"range": {"rent_sek": {"lte": int(max_rent)}}}
            )
        if rooms:
            body["query"]["bool"]["filter"].append(
                {"term": {"rooms": int(rooms)}}
            )
        # [C4] Use native booleans, not string "True"
        if has_balcony and has_balcony.lower() == "true":
            body["query"]["bool"]["filter"].append(
                {"term": {"has_balcony": True}}
            )
        if allows_pets and allows_pets.lower() == "true":
            body["query"]["bool"]["filter"].append(
                {"term": {"allows_pets": True}}
            )

        body["aggs"] = {
            "by_district": {"terms": {"field": "district.raw", "size": 15}},
            "rent_stats": {"stats": {"field": "rent_sek"}},
        }

        offset = (page - 1) * page_size
        response = es.search(index=ES_INDEX, body=body,
                             from_=offset, size=page_size)

        hits = response["hits"]
        total = hits["total"]["value"]
        results = [hit["_source"] for hit in hits["hits"]]

        facets = {}
        if "aggregations" in response:
            aggs = response["aggregations"]
            facets["by_district"] = [
                {"district": b["key"], "count": b["doc_count"]}
                for b in aggs.get("by_district", {}).get("buckets", [])
            ]
            facets["rent_stats"] = aggs.get("rent_stats", {})

        return Response({
            "count": total,
            "page": page,
            "total_pages": (total + page_size - 1) // page_size,
            "results": results,
            "facets": facets,
            "engine": "elasticsearch",
        })

    def _postgres_fallback(self, query, max_rent, rooms, has_balcony,
                            allows_pets, page, page_size):
        """ILIKE-based search when Elasticsearch is unavailable."""
        qs = (
            Listing.objects
            .select_related("landlord", "municipality")
            .annotate(applicant_count=Count("queue_entries"))
            .filter(status=Listing.Status.ACTIVE)
        )

        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(district__icontains=query)
                | Q(street_address__icontains=query)
                | Q(municipality__name__icontains=query)
            )

        if max_rent:
            qs = qs.filter(rent_sek__lte=int(max_rent))
        if rooms:
            qs = qs.filter(rooms=int(rooms))
        if has_balcony and has_balcony.lower() == "true":
            qs = qs.filter(has_balcony=True)
        if allows_pets and allows_pets.lower() == "true":
            qs = qs.filter(allows_pets=True)

        total = qs.count()
        offset = (page - 1) * page_size
        listings = qs[offset:offset + page_size]
        serializer = ListingListSerializer(listings, many=True)

        # [M9] Build facets consistent with ES response structure
        facets = {
            "by_district": list(
                qs.values("district")
                .annotate(count=Count("id"))
                .order_by("-count")[:15]
            ),
            "rent_stats": qs.aggregate(
                min=Min("rent_sek"), max=Max("rent_sek"), avg=Avg("rent_sek"),
            ),
        }

        return Response({
            "count": total,
            "page": page,
            "total_pages": (total + page_size - 1) // page_size,
            "results": serializer.data,
            "facets": facets,
            "engine": "postgres_fallback",
        })


class IndexListingsView(APIView):
    """
    POST /api/search/index/
    Bulk index all active listings into Elasticsearch.
    """

    def post(self, request):
        es = _get_es_client()

        listings = (
            Listing.objects
            .select_related("landlord", "municipality")
            .filter(status=Listing.Status.ACTIVE)
        )

        from elasticsearch.helpers import bulk

        actions = []
        for listing in listings:
            actions.append({
                "_index": ES_INDEX,
                "_id": listing.pk,
                "_source": {
                    "title": listing.title,
                    "description": listing.description,
                    "street_address": listing.street_address,
                    "district": listing.district,
                    "municipality": (
                        listing.municipality.name if listing.municipality else ""
                    ),
                    "city": listing.city,
                    "listing_type": listing.listing_type,
                    "status": listing.status,
                    "rooms": listing.rooms,
                    "size_sqm": listing.size_sqm,
                    "rent_sek": listing.rent_sek,
                    # [C4] Index as native booleans, not strings
                    "has_balcony": listing.has_balcony,
                    "has_parking": listing.has_parking,
                    "allows_pets": listing.allows_pets,
                    "landlord_name": listing.landlord.name,
                    "rent_value": float(listing.rent_sek),
                },
            })

        if actions:
            success, errors = bulk(es, actions, raise_on_error=False)
            return Response({
                "indexed": success,
                "errors": len(errors) if isinstance(errors, list) else 0,
            })

        return Response({"indexed": 0, "errors": 0})
