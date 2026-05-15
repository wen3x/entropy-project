from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .streaks import process_daily_login


def vitality_exempt_paths():
    login_path = reverse("login")
    register_path = reverse("register")
    expired_path = reverse("vitality_expired")
    return frozenset({login_path, register_path, expired_path})


class VitalityMiddleware:
    """Проверяет vitality_expires_at; истёкший аккаунт выходит из сессии."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._exempt = vitality_exempt_paths()

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and request.path not in self._exempt
            and request.user.vitality_expires_at <= timezone.now()
        ):
            logout(request)
            return redirect(reverse("vitality_expired"))

        return self.get_response(request)


class DailyStreakMiddleware:
    """Один раз в день обновляет стрик и начисляет награду при активности пользователя."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._exempt = vitality_exempt_paths()

    def __call__(self, request):
        if request.user.is_authenticated and request.path not in self._exempt:
            summary = process_daily_login(request.user)
            if summary:
                request.session["streak_reward"] = summary
                request.user.refresh_from_db()
                day = summary["streak_day"]
                reward = summary["tokens_reward"]
                if summary["has_free_post"]:
                    messages.success(
                        request,
                        f"День {day} стрика! Вы получили право на один бесплатный пост.",
                    )
                elif reward:
                    messages.success(
                        request,
                        f"День {day} стрика: +{reward} токенов.",
                    )
                else:
                    messages.info(request, f"День {day} стрика. Продолжайте завтра!")

        return self.get_response(request)
