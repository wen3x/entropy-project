import random
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import User
from .quests import award_random_theme_for_user

STREAK_MAX_DAYS = 28

# Диапазоны наград по неделям (хаотичные, random в диапазоне)
WEEKLY_RANGES = {
    1: (10, 20),   # неделя 1: дни 2-6
    2: (15, 25),   # неделя 2: дни 8-13
    3: (15, 30),   # неделя 3: дни 15-20
    4: (25, 30),   # неделя 4: дни 22-28
}

# Дни, когда даётся бесплатный пост (7, 14, 21 — каждый 7-й, кроме 28)
STREAK_FREE_POST_DAYS = frozenset({7, 14, 21})


def _get_week(day: int) -> int:
    return (day - 1) // 7 + 1


def _get_tokens_for_day(day: int) -> int:
    week = _get_week(day)
    lo, hi = WEEKLY_RANGES.get(week, (10, 20))
    return random.randint(lo, hi)


def _range_str(day: int) -> str:
    week = _get_week(day)
    lo, hi = WEEKLY_RANGES.get(week, (10, 20))
    if lo == hi:
        return str(lo)
    return f"{lo}–{hi}"


def _generate_schedule() -> list[dict]:
    """Сгенерировать расписание для отображения (показывает диапазоны)."""
    schedule = []
    for day in range(1, STREAK_MAX_DAYS + 1):
        entry = {"day": day, "label": f"День {day}"}
        if day == 1:
            entry["description"] = "Первый вход — Заряд начат"
            entry["tokens"] = 0
        elif day in STREAK_FREE_POST_DAYS:
            entry["description"] = "Бесплатный пост"
            entry["free_post"] = True
            entry["tokens"] = 0
        elif day == 28:
            entry["description"] = f"{_range_str(day)} токенов + новая тема профиля"
            entry["tokens"] = _range_str(day)
            entry["theme"] = "🎨"
        else:
            entry["description"] = f"Ежедневная награда ({_range_str(day)} токенов)"
            entry["tokens"] = _range_str(day)
        schedule.append(entry)
    return schedule


STREAK_SCHEDULE = _generate_schedule()


def process_daily_login(user: User) -> dict | None:
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

        tokens_reward = 0
        free_posts_awarded = 0
        theme_awarded = None

        updates = {
            "login_streak": new_streak,
            "last_streak_claim": today,
        }

        if new_streak in STREAK_FREE_POST_DAYS:
            updates["free_posts"] = F("free_posts") + 1
            free_posts_awarded = 1
        elif new_streak >= 2:
            tokens_reward = _get_tokens_for_day(new_streak)
            updates["tokens"] = F("tokens") + tokens_reward

        # 28 день — особая награда (токены + тема)
        if new_streak == 28:
            theme_key = award_random_theme_for_user(locked.pk)
            if theme_key:
                from .shop import COLOR_NAMES
                theme_awarded = COLOR_NAMES.get(theme_key, theme_key)

        User.objects.filter(pk=locked.pk).update(**updates)
        locked.refresh_from_db()

    result = {
        "streak_day": new_streak,
        "tokens_reward": tokens_reward,
        "free_posts_awarded": free_posts_awarded,
    }
    if theme_awarded:
        result["theme_awarded"] = theme_awarded
    return result


def get_streak_page_context(user: User) -> dict:
    current = user.login_streak or 0
    progress_pct = (
        min(100, int((current / STREAK_MAX_DAYS) * 100)) if current else 0
    )

    today = timezone.localdate()
    calendar_days = []
    last_claim = user.last_streak_claim

    if last_claim and current > 0:
        streak_broken = (last_claim < today - timedelta(days=1))
    else:
        streak_broken = True

    for offset in range(60):
        day = today - timedelta(days=59 - offset)
        is_active = False
        tooltip = ""

        if last_claim and current > 0 and not streak_broken:
            days_from_last_claim = (last_claim - day).days
            if 0 <= days_from_last_claim < current:
                is_active = True
                tooltip = f"День Заряда {current - days_from_last_claim}"

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
        "free_posts": user.free_posts,
        "calendar_days": calendar_days,
    }
