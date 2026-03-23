"""API views for applications."""
from rest_framework import viewsets

from .models import Application
from .serializers import ApplicationSerializer


class ApplicationViewSet(viewsets.ModelViewSet):
    """Full CRUD for rental applications."""
    queryset = Application.objects.select_related("listing")
    serializer_class = ApplicationSerializer
    filterset_fields = ["listing", "status"]
    ordering_fields = ["submitted_at", "monthly_income_sek"]
    search_fields = ["applicant_name", "applicant_email"]
