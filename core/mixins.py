from typing import Any
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse


class CompanyAdminMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Security mixin enforcing that the requesting user is authenticated
    and possesses Company Owner (ADMIN) privileges.
    """

    def test_func(self) -> bool:
        user = self.request.user
        return bool(
            user.is_authenticated
            and getattr(user, "is_company_admin", False)
            and user.company is not None
        )

    def handle_no_permission(self) -> HttpResponse:
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied("You do not have administrative privileges for this company.")
