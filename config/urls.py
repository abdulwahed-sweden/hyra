"""Hyra URL configuration."""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import TemplateView


def health_check(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("admin/", admin.site.urls),
    path("api/listings/", include("apps.listings.urls")),
    path("api/queue/", include("apps.queue.urls")),
    path("api/search/", include("apps.search.urls")),
    path("api/applications/", include("apps.applications.urls")),
    path("dashboard/", TemplateView.as_view(template_name="dashboard.html"), name="dashboard"),
    path("", TemplateView.as_view(template_name="landing.html"), name="landing"),
]
