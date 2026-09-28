import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.html import strip_tags
from django.views import View
from django.views.generic import DeleteView, FormView, ListView, TemplateView

from .forms import (
    AcceptInviteForm,
    CompanyOwnerSignUpForm,
    EmailAuthenticationForm,
    WorkerInviteForm,
)
from .mixins import CompanyAdminMixin
from .models import Company, Invitation, User


class OwnerSignUpView(FormView):
    """
    Public registration endpoint for Company Owners.
    Creates tenant Company and Owner User records atomically.
    """

    template_name = "accounts/signup.html"
    form_class = CompanyOwnerSignUpForm
    success_url = reverse_lazy("dashboard")

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form: CompanyOwnerSignUpForm) -> HttpResponse:
        company_name = form.cleaned_data["company_name"]
        first_name = form.cleaned_data["first_name"]
        last_name = form.cleaned_data["last_name"]
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]

        with transaction.atomic():
            # Create Tenant Organization
            company = Company.objects.create(name=company_name)

            # Create Company Owner User
            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=User.Roles.ADMIN,
                company=company,
            )

        # Authenticate and login session
        login(self.request, user)
        messages.success(
            self.request,
            f"Welcome to WorkHub! Your company '{company.name}' has been created successfully.",
        )
        return HttpResponseRedirect(self.get_success_url())


class LoginUserView(FormView):
    """
    Email-based authentication view.
    """

    template_name = "accounts/login.html"
    form_class = EmailAuthenticationForm
    success_url = reverse_lazy("dashboard")

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form: EmailAuthenticationForm) -> HttpResponse:
        user = form.get_user()
        if user is not None:
            login(self.request, user)
            messages.info(self.request, f"Welcome back, {user.first_name or user.email}!")
        return HttpResponseRedirect(self.get_success_url())


class LogoutUserView(View):
    """
    Standard logout handler supporting both GET and POST requests.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        logout(request)
        messages.info(request, "You have been successfully logged out.")
        return redirect("login")

    def get(self, request: HttpRequest) -> HttpResponse:
        return self.post(request)


class AcceptInviteView(View):
    """
    Worker invitation acceptance endpoint.
    Validates token integrity, verifies temporary password, and stores
    the permanent updated password in the database.
    """

    template_name = "accounts/accept_invite.html"

    def get_invitation(self, token: str) -> Invitation | None:
        try:
            return Invitation.objects.select_related("company").get(token=token)
        except Invitation.DoesNotExist:
            return None

    def get_or_create_worker_user(self, invitation: Invitation) -> User:
        user = User.objects.filter(email__iexact=invitation.email).first()
        if not user:
            user = User.objects.create_user(
                email=invitation.email,
                password="12345",
                role=User.Roles.WORKER,
                company=invitation.company,
            )
        return user

    def get(self, request: HttpRequest, token: str) -> HttpResponse:
        invitation = self.get_invitation(token)
        if not invitation or not invitation.is_valid():
            return render(
                request,
                self.template_name,
                {"invalid_or_expired": True, "token": token},
                status=400,
            )

        user = self.get_or_create_worker_user(invitation)
        form = AcceptInviteForm(user=user)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "invitation": invitation,
                "worker_user": user,
                "invalid_or_expired": False,
            },
        )

    def post(self, request: HttpRequest, token: str) -> HttpResponse:
        invitation = self.get_invitation(token)
        if not invitation or not invitation.is_valid():
            return render(
                request,
                self.template_name,
                {"invalid_or_expired": True, "token": token},
                status=400,
            )

        user = self.get_or_create_worker_user(invitation)
        form = AcceptInviteForm(user, request.POST)

        if form.is_valid():
            first_name = form.cleaned_data["first_name"]
            last_name = form.cleaned_data["last_name"]
            new_password = form.cleaned_data["new_password"]

            with transaction.atomic():
                # Update user profile and set permanent hashed password in DB
                user.first_name = first_name
                user.last_name = last_name
                user.role = User.Roles.WORKER
                user.company = invitation.company
                user.set_password(new_password)
                user.save()

                # Mark invitation as accepted
                invitation.is_accepted = True
                invitation.save(update_fields=["is_accepted"])

            # Establish session
            login(request, user)
            messages.success(
                request,
                f"Your permanent password has been updated and saved! Welcome to {invitation.company.name}.",
            )
            return redirect("dashboard")

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "invitation": invitation,
                "worker_user": user,
                "invalid_or_expired": False,
            },
        )


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    Role-Aware Dashboard view dynamically rendering owner metrics or worker overview.
    """

    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user: User = self.request.user  # type: ignore
        company = user.company

        context["company"] = company
        context["is_admin"] = user.is_company_admin

        if user.is_company_admin and company:
            # Multi-tenant isolated aggregation metrics
            now = timezone.now()
            context["total_workers"] = User.objects.filter(
                company=company,
                role=User.Roles.WORKER,
            ).count()
            context["active_users"] = User.objects.filter(
                company=company,
                is_active=True,
            ).count()
            context["pending_invites"] = Invitation.objects.filter(
                company=company,
                is_accepted=False,
                expires_at__gt=now,
            ).count()
            context["recent_workers"] = User.objects.filter(
                company=company,
                role=User.Roles.WORKER,
            ).order_by("-date_joined")[:5]
            context["recent_invitations"] = Invitation.objects.filter(
                company=company,
                is_accepted=False,
                expires_at__gt=now,
            ).order_by("-created_at")[:5]
        else:
            # Worker context
            context["colleagues_count"] = (
                User.objects.filter(company=company, is_active=True).count()
                if company
                else 0
            )

        return context


class WorkerListView(CompanyAdminMixin, ListView):
    """
    Tenant-isolated list of all workers belonging to the logged-in owner's company.
    """

    model = User
    template_name = "workers/worker_list.html"
    context_object_name = "workers"
    paginate_by = 15

    def get_queryset(self) -> Any:
        return User.objects.filter(
            company=self.request.user.company,
            role=User.Roles.WORKER,
        ).order_by("-date_joined")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        context["pending_invitations"] = Invitation.objects.filter(
            company=self.request.user.company,
            is_accepted=False,
            expires_at__gt=now,
        ).order_by("-created_at")
        return context


class WorkerInviteView(CompanyAdminMixin, FormView):
    """
    Allows Company Owners to invite new workers via rich HTML and plain-text email dispatch.
    Pre-allots the worker user with default temporary credentials (12345) and generates
    a 32-character hexadecimal token.
    """

    template_name = "workers/invite_worker.html"
    form_class = WorkerInviteForm
    success_url = reverse_lazy("worker_list")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["company"] = self.request.user.company
        return kwargs

    def form_valid(self, form: WorkerInviteForm) -> HttpResponse:
        email = form.cleaned_data["email"]
        company = self.request.user.company

        # Clean 32-hex character token
        token = uuid.uuid4().hex
        expires_at = timezone.now() + timedelta(hours=48)

        with transaction.atomic():
            # Invalidate any older unaccepted invitation for this email
            Invitation.objects.filter(company=company, email__iexact=email, is_accepted=False).delete()

            # Create fresh invitation
            invitation = Invitation.objects.create(
                email=email,
                company=company,
                token=token,
                expires_at=expires_at,
            )

            # Pre-allot user account in DB with initial temporary password '12345'
            worker_user = User.objects.filter(email__iexact=email).first()
            if not worker_user:
                worker_user = User.objects.create_user(
                    email=email,
                    password="12345",
                    role=User.Roles.WORKER,
                    company=company,
                )
            else:
                worker_user.company = company
                worker_user.role = User.Roles.WORKER
                worker_user.set_password("12345")
                worker_user.save()

        # Build invite acceptance URL
        invite_url = self.request.build_absolute_uri(
            reverse("accept_invite", kwargs={"token": invitation.token})
        )

        email_subject = f"Invitation to join {company.name} on WorkHub"
        inviter_name = self.request.user.get_full_name() or self.request.user.email

        email_context = {
            "company": company,
            "inviter_name": inviter_name,
            "email": email,
            "invite_url": invite_url,
        }

        # Render rich HTML email template & plain text fallback
        html_content = render_to_string("emails/worker_invitation.html", email_context)
        plain_text_content = (
            f"Hello,\n\n"
            f"You have been invited by {inviter_name} to join the team at {company.name} on WorkHub.\n\n"
            f"Account Details:\n"
            f"- Email: {email}\n"
            f"- Temporary Password: 12345\n\n"
            f"To complete your onboarding and choose your permanent password, click the link below:\n\n"
            f"{invite_url}\n\n"
            f"This link expires in 48 hours.\n\n"
            f"Best regards,\nThe WorkHub Team"
        )

        # Dispatch real multi-alternative email (HTML + Plain Text)
        msg = EmailMultiAlternatives(
            subject=email_subject,
            body=plain_text_content,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@workhub.internal"),
            to=[email],
        )
        msg.attach_alternative(html_content, "text/html")

        try:
            msg.send(fail_silently=False)
            messages.success(
                self.request,
                f"Invitation successfully dispatched to {email}. An email with setup instructions and the temporary password (12345) has been sent to their inbox.",
            )
        except Exception as exc:
            messages.error(
                self.request,
                f"Could not connect to Gmail SMTP: {exc}. Please verify your 16-character Google App Password in settings.py.",
            )

        return HttpResponseRedirect(self.get_success_url())


class WorkerDeleteView(CompanyAdminMixin, DeleteView):
    """
    Tenant-isolated worker deletion view.
    Ensures an owner can only delete workers belonging strictly to their company.
    """

    model = User
    template_name = "workers/worker_confirm_delete.html"
    context_object_name = "worker"
    success_url = reverse_lazy("worker_list")

    def get_queryset(self) -> Any:
        return User.objects.filter(
            company=self.request.user.company,
            role=User.Roles.WORKER,
        )

    def delete(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        worker = self.get_object()
        worker_email = worker.email
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f"Worker {worker_email} has been successfully removed.")
        return response
