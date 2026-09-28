from django.urls import path
from . import views

urlpatterns = [
    # Authentication & Onboarding
    path("signup/", views.OwnerSignUpView.as_view(), name="signup"),
    path("login/", views.LoginUserView.as_view(), name="login"),
    path("logout/", views.LogoutUserView.as_view(), name="logout"),
    path("invite/accept/<str:token>/", views.AcceptInviteView.as_view(), name="accept_invite"),

    # Tenant Dashboard (Role-Aware)
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),

    # Worker Management (Owner-only tenant isolated)
    path("workers/", views.WorkerListView.as_view(), name="worker_list"),
    path("workers/invite/", views.WorkerInviteView.as_view(), name="invite_worker"),
    path("workers/<int:pk>/delete/", views.WorkerDeleteView.as_view(), name="delete_worker"),
]
