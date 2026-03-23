"""Hyra URL configuration."""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/listings/", include("apps.listings.urls")),
    path("api/queue/", include("apps.queue.urls")),
    path("api/search/", include("apps.search.urls")),
    path("api/applications/", include("apps.applications.urls")),
    path("", TemplateView.as_view(template_name="dashboard.html"), name="dashboard"),
]
