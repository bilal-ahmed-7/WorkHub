import uuid
from datetime import datetime
from typing import Any, Optional

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager["User"]):
    """
    Custom manager for User model where email is the unique identifier
    for authentication instead of usernames.
    """

    def create_user(
        self,
        email: str,
        password: Optional[str] = None,
        **extra_fields: Any,
    ) -> "User":
        """Create and save a standard user with the given email and password."""
        if not email:
            raise ValueError(_("The Email field must be set."))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        password: Optional[str] = None,
        **extra_fields: Any,
    ) -> "User":
        """Create and save a superuser with the given email and password."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Roles.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, password, **extra_fields)


class Company(models.Model):
    """
    Tenant entity representing a distinct company organization.
    All users and invitations are scoped to a specific Company tenant.
    """

    name = models.CharField(max_length=255, verbose_name=_("Company Name"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))

    class Meta:
        verbose_name = _("Company")
        verbose_name_plural = _("Companies")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class User(AbstractUser):
    """
    Custom User model supporting multi-tenant role-based access control (RBAC).
    Usernames are omitted in favor of unique Email addresses.
    """

    class Roles(models.TextChoices):
        ADMIN = "ADMIN", _("Company Owner")
        WORKER = "WORKER", _("Worker")

    username = None  # Remove username field
    email = models.EmailField(_("Email Address"), unique=True)
    role = models.CharField(
        max_length=10,
        choices=Roles.choices,
        default=Roles.WORKER,
        verbose_name=_("Role"),
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
        verbose_name=_("Company"),
    )

    objects: CustomUserManager = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        ordering = ["first_name", "last_name", "email"]

    def __str__(self) -> str:
        full_name = self.get_full_name()
        return f"{full_name} ({self.email})" if full_name else self.email

    @property
    def is_company_admin(self) -> bool:
        """Helper property verifying if the user has Company Owner permissions."""
        return self.role == self.Roles.ADMIN


class Invitation(models.Model):
    """
    Represents an invitation token sent to prospective workers for tenant onboarding.
    Tokens expire after a set time window (default 48 hours).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(verbose_name=_("Worker Email"))
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="invitations",
        verbose_name=_("Company"),
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        verbose_name=_("Security Token"),
    )
    is_accepted = models.BooleanField(
        default=False,
        verbose_name=_("Is Accepted"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
    )
    expires_at = models.DateTimeField(
        verbose_name=_("Expires At"),
    )

    class Meta:
        verbose_name = _("Invitation")
        verbose_name_plural = _("Invitations")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Invite to {self.email} for {self.company.name}"

    def is_valid(self) -> bool:
        """
        Validates whether the invitation has not yet been accepted
        and has not expired past its expiration timestamp.
        """
        return not self.is_accepted and timezone.now() <= self.expires_at
