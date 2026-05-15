from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("expired/", views.vitality_expired, name="vitality_expired"),
    path("profile/", views.profile_redirect, name="profile"),
    path("profile/<int:user_id>/", views.profile_detail, name="profile_detail"),
    path("streaks/", views.streaks_page, name="streaks"),
    path("notifications/", views.notifications_list, name="notifications_list"),
    path(
        "notifications/read/",
        views.notifications_mark_read,
        name="notifications_mark_read",
    ),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
]
