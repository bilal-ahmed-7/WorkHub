from typing import Any
from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import Company, Invitation, User

UserModel = get_user_model()


class CompanyOwnerSignUpForm(forms.Form):
    """
    Form for atomic public registration of a new Company and its Owner User.
    """

    company_name = forms.CharField(
        max_length=255,
        required=True,
        label=_("Company Name"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Acme Innovations Inc.",
            "autocomplete": "organization",
        }),
    )
    first_name = forms.CharField(
        max_length=150,
        required=True,
        label=_("First Name"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Jane",
            "autocomplete": "given-name",
        }),
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        label=_("Last Name"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Doe",
            "autocomplete": "family-name",
        }),
    )
    email = forms.EmailField(
        required=True,
        label=_("Work Email Address"),
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "jane@acme.com",
            "autocomplete": "email",
        }),
    )
    password = forms.CharField(
        required=True,
        label=_("Password"),
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "••••••••",
            "autocomplete": "new-password",
        }),
    )
    confirm_password = forms.CharField(
        required=True,
        label=_("Confirm Password"),
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "••••••••",
            "autocomplete": "new-password",
        }),
    )

    def clean_email(self) -> str:
        email = self.cleaned_data.get("email", "").strip().lower()
        if UserModel.objects.filter(email__iexact=email).exists():
            raise ValidationError(_("A user with this email address already exists."))
        return email

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password:
            if password != confirm_password:
                self.add_error("confirm_password", _("Passwords do not match."))
            else:
                validate_password(password)

        return cleaned_data


class EmailAuthenticationForm(forms.Form):
    """
    Custom authentication form accepting email and password for login.
    """

    email = forms.EmailField(
        required=True,
        label=_("Email Address"),
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "name@company.com",
            "autocomplete": "email",
            "autofocus": True,
        }),
    )
    password = forms.CharField(
        required=True,
        label=_("Password"),
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "••••••••",
            "autocomplete": "current-password",
        }),
    )

    def __init__(self, request: Any = None, *args: Any, **kwargs: Any) -> None:
        self.request = request
        self.user_cache: User | None = None
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        email = cleaned_data.get("email", "").strip().lower()
        password = cleaned_data.get("password")

        if email and password:
            self.user_cache = authenticate(
                self.request,
                email=email,
                password=password,
            )
            if self.user_cache is None:
                raise ValidationError(
                    _("Invalid email address or password. Please try again."),
                    code="invalid_login",
                )
            elif not self.user_cache.is_active:
                raise ValidationError(
                    _("This account is currently deactivated."),
                    code="inactive",
                )

        return cleaned_data

    def get_user(self) -> User | None:
        return self.user_cache


class WorkerInviteForm(forms.Form):
    """
    Form for Company Owners to dispatch invitations to prospective workers.
    Allows re-inviting / refreshing invites seamlessly.
    """

    email = forms.EmailField(
        required=True,
        label=_("Worker Email Address"),
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "colleague@company.com",
            "autocomplete": "email",
        }),
    )

    def __init__(self, company: Company, *args: Any, **kwargs: Any) -> None:
        self.company = company
        super().__init__(*args, **kwargs)

    def clean_email(self) -> str:
        email = self.cleaned_data.get("email", "").strip().lower()

        # If user is already active and verified in this company (and no pending unaccepted invite)
        existing_user = UserModel.objects.filter(email__iexact=email).first()
        has_pending_invite = Invitation.objects.filter(
            company=self.company,
            email__iexact=email,
            is_accepted=False,
        ).exists()

        if existing_user and existing_user.company == self.company and not has_pending_invite:
            # Check if user has already set a permanent password / is active member
            if existing_user.first_name:
                raise ValidationError(
                    _("This user is already an active verified member of your company.")
                )

        return email


class AcceptInviteForm(forms.Form):
    """
    Form presented to an invited worker to validate temporary credentials
    and update their profile and permanent password.
    """

    temp_password = forms.CharField(
        required=True,
        label=_("Temporary / Initial Password"),
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Enter temporary password (e.g. 12345)",
            "autocomplete": "current-password",
        }),
        help_text=_("Enter the initial temporary password provided in your invitation (default: 12345)."),
    )
    first_name = forms.CharField(
        max_length=150,
        required=True,
        label=_("First Name"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Bilal",
            "autocomplete": "given-name",
        }),
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        label=_("Last Name"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Mateen",
            "autocomplete": "family-name",
        }),
    )
    new_password = forms.CharField(
        required=True,
        label=_("New Permanent Password"),
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Choose your secure password",
            "autocomplete": "new-password",
        }),
    )
    confirm_new_password = forms.CharField(
        required=True,
        label=_("Confirm New Password"),
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Confirm your secure password",
            "autocomplete": "new-password",
        }),
    )

    def __init__(self, user: User, *args: Any, **kwargs: Any) -> None:
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_temp_password(self) -> str:
        temp_password = self.cleaned_data.get("temp_password")
        if not self.user.check_password(temp_password) and temp_password != "12345":
            raise ValidationError(_("The temporary password you entered is incorrect."))
        return temp_password

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_new_password = cleaned_data.get("confirm_new_password")

        if new_password and confirm_new_password:
            if new_password != confirm_new_password:
                self.add_error("confirm_new_password", _("Passwords do not match."))
            else:
                validate_password(new_password)

        return cleaned_data
