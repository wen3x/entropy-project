from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import User, UserDailyQuestCycle
from .notifications import notify_quest_complete

CYCLE_COOLDOWN = timedelta(hours=24)

DAILY_QUEST_DEFS = (
    {
        "key": "golden_likes",
        "title": "Золотой интерес",
        "description": "Поставьте лайк на 3 разных золотых поста.",
        "target": 3,
        "reward_label": "+100 токенов",
        "reward_tokens": 100,
    },
    {
        "key": "golden_approval",
        "title": "Одобренное мнение",
        "description": "Получите одобрение комментария к золотому посту.",
        "target": 1,
        "reward_label": "Бесплатный пост",
        "free_post": True,
    },
    {
        "key": "dying_extensions",
        "title": "Спаситель",
        "description": "Продлите жизнь 5 постам, у которых осталось менее 24 часов.",
        "target": 5,
        "reward_label": "+150 токенов",
        "reward_tokens": 150,
    },
    {
        "key": "comment_streak",
        "title": "Душа компании",
        "description": "Оставьте 3 комментария к разным постам (не золотым).",
        "target": 3,
        "reward_label": "+40 токенов",
        "reward_tokens": 40,
    },
    {
        "key": "post_and_earn",
        "title": "Генератор контента",
        "description": "Создайте пост, который наберёт хотя бы 5 лайков.",
        "target": 5,
        "reward_label": "+100 токенов",
        "reward_tokens": 100,
    },
    {
        "key": "near_death",
        "title": "На краю",
        "description": "Оставьте комментарий к посту, которому осталось жить меньше 1 часа.",
        "target": 1,
        "reward_label": "+75 токенов",
        "reward_tokens": 75,
    },      
)


def _maybe_start_new_cycle(cycle: UserDailyQuestCycle) -> UserDailyQuestCycle:
    if not cycle.cycle_completed_at:
        return cycle
    if timezone.now() < cycle.cycle_completed_at + CYCLE_COOLDOWN:
        return cycle
    cycle.cycle_started_at = timezone.now()
    cycle.cycle_completed_at = None
    cycle.golden_likes_done = False
    cycle.golden_approval_done = False
    cycle.dying_extensions_done = False
    cycle.golden_liked_post_ids = []
    cycle.dying_extended_post_ids = []
    cycle.save()
    return cycle


def get_or_create_cycle(user: User) -> UserDailyQuestCycle:
    cycle, _ = UserDailyQuestCycle.objects.get_or_create(user=user)
    return _maybe_start_new_cycle(cycle)


def _grant_quest_reward(cycle: UserDailyQuestCycle, quest_def: dict) -> None:
    if quest_def.get("free_post"):
        User.objects.filter(pk=cycle.user_id).update(has_free_post=True)
        notify_quest_complete(cycle.user, quest_def["title"], free_post=True)
        return
    tokens = quest_def.get("reward_tokens", 0)
    if tokens:
        User.objects.filter(pk=cycle.user_id).update(tokens=F("tokens") + tokens)
    notify_quest_complete(cycle.user, quest_def["title"], tokens)


def _check_cycle_complete(cycle: UserDailyQuestCycle) -> None:
    if cycle.cycle_completed_at:
        return
    if (
        cycle.golden_likes_done
        and cycle.golden_approval_done
        and cycle.dying_extensions_done
    ):
        cycle.cycle_completed_at = timezone.now()
        cycle.save(update_fields=["cycle_completed_at"])


def _complete_quest_step(cycle: UserDailyQuestCycle, quest_key: str) -> None:
    quest_def = next(q for q in DAILY_QUEST_DEFS if q["key"] == quest_key)
    field_map = {
        "golden_likes": "golden_likes_done",
        "golden_approval": "golden_approval_done",
        "dying_extensions": "dying_extensions_done",
    }
    field = field_map[quest_key]
    if getattr(cycle, field):
        return
    setattr(cycle, field, True)
    cycle.save(update_fields=[field])
    _grant_quest_reward(cycle, quest_def)
    cycle.refresh_from_db()
    _check_cycle_complete(cycle)


def on_golden_post_liked(user: User, post_id: int) -> None:
    if not user.is_authenticated:
        return
    with transaction.atomic():
        cycle = get_or_create_cycle(user)
        if cycle.golden_likes_done:
            return
        ids = list(cycle.golden_liked_post_ids or [])
        if post_id in ids:
            return
        ids.append(post_id)
        cycle.golden_liked_post_ids = ids
        cycle.save(update_fields=["golden_liked_post_ids"])
        if len(ids) >= DAILY_QUEST_DEFS[0]["target"]:
            _complete_quest_step(cycle, "golden_likes")


def on_golden_comment_approved(comment_author: User) -> None:
    with transaction.atomic():
        cycle = get_or_create_cycle(comment_author)
        if cycle.golden_approval_done:
            return
        _complete_quest_step(cycle, "golden_approval")


def on_post_life_extended(user: User, post_id: int, hours_remaining_before: float) -> None:
    if hours_remaining_before >= 24:
        return
    with transaction.atomic():
        cycle = get_or_create_cycle(user)
        if cycle.dying_extensions_done:
            return
        ids = list(cycle.dying_extended_post_ids or [])
        if post_id in ids:
            return
        ids.append(post_id)
        cycle.dying_extended_post_ids = ids
        cycle.save(update_fields=["dying_extended_post_ids"])
        if len(ids) >= DAILY_QUEST_DEFS[2]["target"]:
            _complete_quest_step(cycle, "dying_extensions")


def get_daily_quests_context(user: User) -> dict:
    cycle = get_or_create_cycle(user)
    items = []
    for quest_def in DAILY_QUEST_DEFS:
        key = quest_def["key"]
        if key == "golden_likes":
            progress = len(cycle.golden_liked_post_ids or [])
            done = cycle.golden_likes_done
        elif key == "golden_approval":
            progress = 1 if cycle.golden_approval_done else 0
            done = cycle.golden_approval_done
        else:
            progress = len(cycle.dying_extended_post_ids or [])
            done = cycle.dying_extensions_done
        items.append(
            {
                **quest_def,
                "progress": progress,
                "completed": done,
            }
        )
    next_cycle_at = None
    if cycle.cycle_completed_at:
        next_cycle_at = cycle.cycle_completed_at + CYCLE_COOLDOWN
    return {
        "daily_quest_items": items,
        "daily_cycle_completed": bool(cycle.cycle_completed_at),
        "daily_next_cycle_at": next_cycle_at,
    }
