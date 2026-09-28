"""
WorkHub URL Configuration.
The default Django Admin ('/admin/') is intentionally excluded for security.
"""

from django.shortcuts import redirect
from django.urls import include, path

urlpatterns = [
    # Root redirect
    path("", lambda request: redirect("dashboard" if request.user.is_authenticated else "signup"), name="root"),
    # Core app routes
    path("", include("core.urls")),
]
