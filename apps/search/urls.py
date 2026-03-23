"""URL routing for search API."""
from django.urls import path

from .views import IndexListingsView, ListingSearchView

urlpatterns = [
    path("", ListingSearchView.as_view(), name="listing-search"),
    path("index/", IndexListingsView.as_view(), name="listing-index"),
]
