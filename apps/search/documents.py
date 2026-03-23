"""Elasticsearch document definition for listings."""
from elasticsearch_dsl import Document, Float, Integer, Keyword, Text


class ListingDocument(Document):
    """ES mapping for rental listings — optimized for Swedish full-text search."""
    title = Text(analyzer="standard", boost=3)
    description = Text(analyzer="standard")
    street_address = Text(analyzer="standard")
    district = Text(analyzer="standard", boost=2, fields={"raw": Keyword()})
    municipality = Text(analyzer="standard", boost=2, fields={"raw": Keyword()})
    city = Text(analyzer="standard")
    listing_type = Keyword()
    status = Keyword()
    rooms = Integer()
    size_sqm = Integer()
    rent_sek = Integer()
    has_balcony = Keyword()
    has_parking = Keyword()
    allows_pets = Keyword()
    landlord_name = Text(analyzer="standard")

    # For filtering/aggregations
    rent_value = Float()

    class Index:
        name = "hyra_listings"
        settings = {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
