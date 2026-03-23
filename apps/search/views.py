"""
Search views — Elasticsearch with automatic Postgres fallback.

The search always returns results: if ES is unavailable, a Postgres
ILIKE query transparently takes over. The response includes an 'engine'
field so the client knows which backend served the results.
"""
import logging

from django.db.models import Count, Q

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError as ESConnectionError
from elastic_transport import ConnectionError as TransportConnectionError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.listings.models import Listing
from apps.listings.serializers import ListingListSerializer

from decouple import config as env_config

logger = logging.getLogger(__name__)


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
        page = int(request.query_params.get("page", 1))
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
        es_url = env_config("ELASTICSEARCH_URL", default="http://localhost:9200")
        es = Elasticsearch([es_url])

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

        # Status filter — only active listings
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
        if has_balcony and has_balcony.lower() == "true":
            body["query"]["bool"]["filter"].append(
                {"term": {"has_balcony": "True"}}
            )
        if allows_pets and allows_pets.lower() == "true":
            body["query"]["bool"]["filter"].append(
                {"term": {"allows_pets": "True"}}
            )

        # Aggregations for faceted search
        body["aggs"] = {
            "by_district": {"terms": {"field": "district.raw", "size": 15}},
            "rent_stats": {"stats": {"field": "rent_sek"}},
        }

        offset = (page - 1) * page_size
        response = es.search(index="hyra_listings", body=body,
                             from_=offset, size=page_size)

        hits = response["hits"]
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
            "count": hits["total"]["value"],
            "page": page,
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

        # Build basic facets from Postgres
        facets = {
            "by_district": list(
                qs.values("district")
                .annotate(count=Count("id"))
                .order_by("-count")[:15]
            ),
        }

        return Response({
            "count": total,
            "page": page,
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
        es_url = env_config("ELASTICSEARCH_URL", default="http://localhost:9200")
        es = Elasticsearch([es_url])

        listings = (
            Listing.objects
            .select_related("landlord", "municipality")
            .filter(status=Listing.Status.ACTIVE)
        )

        # Build bulk actions
        from elasticsearch.helpers import bulk

        actions = []
        for listing in listings:
            actions.append({
                "_index": "hyra_listings",
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
                    "has_balcony": str(listing.has_balcony),
                    "has_parking": str(listing.has_parking),
                    "allows_pets": str(listing.allows_pets),
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
