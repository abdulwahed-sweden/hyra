"""URL routing for queue API."""
from rest_framework.routers import DefaultRouter

from .views import QueueViewSet

router = DefaultRouter()
router.register(r"entries", QueueViewSet, basename="queue-entry")

urlpatterns = router.urls
