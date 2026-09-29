"""
URL configuration for WorkHub backend project.
All API endpoints are namespaced under /api/...
"""

from django.urls import include, path

urlpatterns = [
    # Accounts & Authentication endpoints
    path("api/accounts/", include("accounts.urls")),
    # Company & Worker management endpoints
    path("api/companies/", include("companies.urls")),
    # Invitation endpoints
    path("api/invitations/", include("invitations.urls")),
]
