"""URL routing for listings API."""
from rest_framework.routers import DefaultRouter

from .views import ListingViewSet

router = DefaultRouter()
router.register(r"", ListingViewSet, basename="listing")

urlpatterns = router.urls
