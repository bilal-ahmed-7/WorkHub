from typing import Any
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Tests the live Gmail SMTP connection and sends a sample test email."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--to",
            type=str,
            default=getattr(settings, "EMAIL_HOST_USER", ""),
            help="Recipient email address to test delivery",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        recipient = options.get("to")
        sender = getattr(settings, "EMAIL_HOST_USER", "")
        backend = getattr(settings, "EMAIL_BACKEND", "")

        self.stdout.write(f"Connecting to SMTP Server: {getattr(settings, 'EMAIL_HOST', '')}:{getattr(settings, 'EMAIL_PORT', '')}")
        self.stdout.write(f"Sender (EMAIL_HOST_USER): {sender}")
        self.stdout.write(f"Recipient: {recipient}")
        self.stdout.write(f"Backend: {backend}\n")

        if not sender:
            self.stdout.write(self.style.ERROR("Error: EMAIL_HOST_USER is not set in .env or settings.py"))
            return

        try:
            send_mail(
                subject="WorkHub Live SMTP Test",
                message="Congratulations! Your Django SMTP email configuration is working perfectly.",
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", sender),
                recipient_list=[recipient],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS(f"✅ Success! Test email was successfully delivered to {recipient} via Gmail SMTP!"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"❌ SMTP Failed: {exc}"))
