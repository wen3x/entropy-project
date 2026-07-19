from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import RecaptchaLoginForm

urlpatterns = [
    path("register/", views.register, name="register"),
    path("expired/", views.vitality_expired, name="vitality_expired"),
    path("profile/", views.profile_redirect, name="profile"),
    path("u/@<str:username>/", views.profile_detail, name="profile_detail"),
    # Redirect from old /profile/username/ to /u/@username/
    path("profile/<str:username>/", views.profile_old_redirect, name="profile_detail_old"),
    path("streaks/", views.streaks_page, name="streaks"),
    path("shop/", views.shop_view, name="shop"),
    path("inventory/", views.inventory_view, name="inventory"),
    path("notifications/", views.notifications_list, name="notifications_list"),
    path(
        "notifications/read/",
        views.notifications_mark_read,
        name="notifications_mark_read",
    ),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=RecaptchaLoginForm,
        ),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    # PWA: Push-уведомления
    path("push/subscribe/", views.save_push_subscription, name="save_push_subscription"),
    path("push/unsubscribe/", views.delete_push_subscription, name="delete_push_subscription"),
    path("push/vapid-key/", views.vapid_public_key, name="vapid_public_key"),
    # Онлайн-счётчик
    path("online/", views.online_count, name="online_count"),
    # Бесплатный крон (cron-job.org → этот URL)
    path("cron/send-notifications/", views.cron_trigger, name="cron_trigger"),
    # Жалобы
    path("complaints/", views.complaints_list, name="complaints_list"),
    path("complaints/submit/", views.submit_complaint, name="submit_complaint"),
    path("complaints/<int:pk>/resolve/", views.resolve_complaint, name="resolve_complaint"),
    path("complaints/<int:pk>/dismiss/", views.dismiss_complaint, name="dismiss_complaint"),
    # Юридические страницы
    path("privacy/", views.legal_page, {"slug": "privacy"}, name="privacy_policy"),
    path("terms/", views.legal_page, {"slug": "terms"}, name="terms_of_use"),
]
