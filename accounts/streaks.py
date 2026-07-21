from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import User

STREAK_MAX_DAYS = 14

STREAK_REWARDS = {
    1: 0,
    2: 10,
    3: 15,
    4: 10,
    5: 10,
    6: 10,
    7: 0,
    8: 50,
    9: 20,
    10: 25,
    11: 20,
    12: 25,
    13: 0,
    14: 0,
}

STREAK_FREE_POST_DAYS = frozenset({7, 13, 14})

STREAK_SCHEDULE = [
    {"day": 1, "label": "День 1", "description": "Первый вход - стрик начат", "tokens": 0},
    {"day": 2, "label": "День 2", "description": "Ежедневная награда", "tokens": 10},
    {"day": 3, "label": "День 3", "description": "Ежедневная награда", "tokens": 15},
    {"day": 4, "label": "День 4", "description": "Ежедневная награда", "tokens": 10},
    {"day": 5, "label": "День 5", "description": "Ежедневная награда", "tokens": 10},
    {"day": 6, "label": "День 6", "description": "Ежедневная награда", "tokens": 10},
    {
        "day": 7,
        "label": "День 7",
        "description": "Один бесплатный пост (0 токенов)",
        "tokens": 0,
        "free_post": True,
    },
    {"day": 8, "label": "День 8", "description": "Ежедневная награда", "tokens": 50},
    {"day": 9, "label": "День 9", "description": "Ежедневная награда", "tokens": 20},
    {"day": 10, "label": "День 10", "description": "Ежедневная награда", "tokens": 25},
    {"day": 11, "label": "День 11", "description": "Ежедневная награда", "tokens": 20},
    {"day": 12, "label": "День 12", "description": "Ежедневная награда", "tokens": 25},
    {
        "day": 13,
        "label": "День 13",
        "description": "Один бесплатный пост (0 токенов)",
        "tokens": 0,
        "free_post": True,
    },
    {
        "day": 14,
        "label": "День 14",
        "description": "Один бесплатный пост (0 токенов)",
        "tokens": 0,
        "free_post": True,
    },
]


def process_daily_login(user: User) -> dict | None:
    """Начисляет награду за день, если ещё не забирали сегодня."""
    today = timezone.localdate()

    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)

        if locked.last_streak_claim == today:
            return None

        if locked.last_streak_claim is None:
            new_streak = 1
        elif locked.last_streak_claim == today - timedelta(days=1):
            new_streak = locked.login_streak + 1
        else:
            new_streak = 1

        if new_streak > STREAK_MAX_DAYS:
            new_streak = 1

        tokens_reward = STREAK_REWARDS.get(new_streak, 0)
        updates = {
            "login_streak": new_streak,
            "last_streak_claim": today,
        }
        if tokens_reward:
            updates["tokens"] = F("tokens") + tokens_reward
        if new_streak in STREAK_FREE_POST_DAYS:
            updates["has_free_post"] = True

        User.objects.filter(pk=locked.pk).update(**updates)
        locked.refresh_from_db()

    return {
        "streak_day": new_streak,
        "tokens_reward": tokens_reward,
        "has_free_post": new_streak in STREAK_FREE_POST_DAYS,
    }


def get_streak_page_context(user: User) -> dict:
    current = user.login_streak or 0
    progress_pct = (
        min(100, int((current / STREAK_MAX_DAYS) * 100)) if current else 0
    )

    # ── Календарь: последние 60 дней ──
    today = timezone.localdate()
    calendar_days = []
    last_claim = user.last_streak_claim

    # Вычисляем предполагаемый первый день стрика
    # Если стрик активен, то streak дней подряд до last_claim
    if last_claim and current > 0:
        # Проверяем, не сломан ли стрик (last_claim + 1 день = today)
        streak_broken = (last_claim < today - timedelta(days=1))
    else:
        streak_broken = True

    for offset in range(60):
        day = today - timedelta(days=59 - offset)
        is_active = False
        tooltip = ""

        if last_claim and current > 0 and not streak_broken:
            # Стрик активен — закрашиваем последние `current` дней
            days_from_last_claim = (last_claim - day).days
            if 0 <= days_from_last_claim < current:
                is_active = True
                tooltip = f"День стрика {current - days_from_last_claim}"

        # Отмечаем день когда был заклеймлен
        if last_claim and day == last_claim:
            tooltip = f"Последний вход • {day:%d.%m}"
            if current > 0:
                is_active = True

        calendar_days.append({
            "day": day,
            "is_active": is_active,
            "is_today": day == today,
            "is_future": day > today,
            "tooltip": tooltip or day.strftime("%d.%m.%Y"),
        })

    return {
        "schedule": STREAK_SCHEDULE,
        "current_streak": current,
        "progress_pct": progress_pct,
        "streak_max_days": STREAK_MAX_DAYS,
        "has_free_post": user.has_free_post,
        "calendar_days": calendar_days,
    }
