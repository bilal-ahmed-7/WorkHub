from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from core.models import Company, Invitation

User = get_user_model()


class MultiTenantRBACFlowTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_owner_signup_flow(self) -> None:
        signup_url = reverse("signup")
        payload = {
            "company_name": "Nexus Corp",
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@nexus.test",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
        }
        response = self.client.post(signup_url, payload, follow=True)
        self.assertEqual(response.status_code, 200)

        # Check atomic creation
        self.assertTrue(Company.objects.filter(name="Nexus Corp").exists())
        company = Company.objects.get(name="Nexus Corp")

        user = User.objects.get(email="alice@nexus.test")
        self.assertEqual(user.company, company)
        self.assertEqual(user.role, User.Roles.ADMIN)
        self.assertTrue(user.is_company_admin)

    def test_worker_invite_and_password_update_flow(self) -> None:
        # Create Owner & Company
        company = Company.objects.create(name="Titan Tech")
        owner = User.objects.create_user(
            email="owner@titan.test",
            password="OwnerPassword123!",
            role=User.Roles.ADMIN,
            company=company,
        )
        self.client.force_login(owner)

        # Invite Worker bilalmateen605@gmail.com
        invite_url = reverse("invite_worker")
        response = self.client.post(invite_url, {"email": "bilalmateen605@gmail.com"}, follow=True)
        self.assertEqual(response.status_code, 200)

        # Verify email sent with temporary password details
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Invitation to join Titan Tech", mail.outbox[0].subject)
        self.assertIn("12345", mail.outbox[0].body)

        # Verify Invitation record and pre-allotted worker user created with temp password
        invitation = Invitation.objects.get(email="bilalmateen605@gmail.com", company=company)
        self.assertTrue(invitation.is_valid())
        self.assertFalse(invitation.is_accepted)

        worker_pre = User.objects.get(email="bilalmateen605@gmail.com")
        self.assertTrue(worker_pre.check_password("12345"))

        # Logout owner
        self.client.logout()

        # Worker clicks link and submits temporary password + new permanent password
        accept_url = reverse("accept_invite", kwargs={"token": invitation.token})
        accept_payload = {
            "temp_password": "12345",
            "first_name": "Bilal",
            "last_name": "Mateen",
            "new_password": "MyPermanentPassword99!",
            "confirm_new_password": "MyPermanentPassword99!",
        }
        accept_response = self.client.post(accept_url, accept_payload, follow=True)
        self.assertEqual(accept_response.status_code, 200)

        # Verify worker user now has updated permanent password
        worker = User.objects.get(email="bilalmateen605@gmail.com")
        self.assertEqual(worker.company, company)
        self.assertEqual(worker.role, User.Roles.WORKER)
        self.assertEqual(worker.first_name, "Bilal")
        self.assertEqual(worker.last_name, "Mateen")
        self.assertTrue(worker.check_password("MyPermanentPassword99!"))
        self.assertFalse(worker.check_password("12345"))

        # Verify invitation marked accepted
        invitation.refresh_from_db()
        self.assertTrue(invitation.is_accepted)
        self.assertFalse(invitation.is_valid())

        # Test future login with new permanent password
        self.client.logout()
        login_response = self.client.post(reverse("login"), {
            "email": "bilalmateen605@gmail.com",
            "password": "MyPermanentPassword99!",
        }, follow=True)
        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(login_response.context["user"].is_authenticated)

    def test_tenant_isolation_worker_access(self) -> None:
        company_a = Company.objects.create(name="Company A")
        company_b = Company.objects.create(name="Company B")

        owner_a = User.objects.create_user(
            email="owner_a@a.test",
            password="Password123!",
            role=User.Roles.ADMIN,
            company=company_a,
        )
        worker_b = User.objects.create_user(
            email="worker_b@b.test",
            password="Password123!",
            role=User.Roles.WORKER,
            company=company_b,
        )

        # Owner A logs in and attempts to delete Worker B
        self.client.force_login(owner_a)
        delete_url = reverse("delete_worker", kwargs={"pk": worker_b.pk})
        delete_response = self.client.post(delete_url)
        self.assertEqual(delete_response.status_code, 404)
        self.assertTrue(User.objects.filter(pk=worker_b.pk).exists())
