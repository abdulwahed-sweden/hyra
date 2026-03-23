"""URL routing for applications API."""
from rest_framework.routers import DefaultRouter

from .views import ApplicationViewSet

router = DefaultRouter()
router.register(r"", ApplicationViewSet, basename="application")

urlpatterns = router.urls
