import random
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count, F
from django.utils import timezone

from forum.models import Comment, Like, Post

from .models import Quest, User, UserQuestSlot
from .notifications import notify_quest_complete

QUEST_REFRESH_DAYS = 3
ACTIVE_SLOT_COUNT = 3

QUEST_REGISTRY = {
    "content-star": {
        "title": "Звезда контента",
        "description": "Соберите 5 лайков на одном своём посте.",
        "target": 5,
        "reward_tokens": 40,
        "reward_label": "+40 токенов",
    },
    "discussion": {
        "title": "Дискуссия",
        "description": "Получите 3 комментария от разных пользователей под одним своим постом.",
        "target": 3,
        "reward_tokens": 50,
        "reward_label": "+50 токенов",
    },
    "opinion-leader": {
        "title": "Лидер мнений",
        "description": "Соберите 5 лайков на одном своём комментарии.",
        "target": 5,
        "reward_tokens": 25,
        "reward_label": "+25 токенов",
    },
    "golden_likes": {
        "title": "Золотой интерес",
        "description": "Поставьте лайк на 3 разных золотых поста.",
        "target": 3,
        "reward_tokens": 100,
        "reward_label": "+100 токенов",
    },
    "golden_approval": {
        "title": "Одобренное мнение",
        "description": "Получите одобрение комментария к золотому посту.",
        "target": 1,
        "free_post": True,
        "reward_label": "Бесплатный пост",
    },
    "dying_extensions": {
        "title": "Спаситель",
        "description": "Продлите жизнь 5 постам, у которых осталось менее 24 часов.",
        "target": 5,
        "reward_tokens": 150,
        "reward_label": "+150 токенов",
    },
}

ALL_QUEST_CODES = list(QUEST_REGISTRY.keys())


def ensure_default_quests():
    legacy = (
        ("content-star", Quest.QuestType.POST_LIKES, 5, 40),
        ("discussion", Quest.QuestType.POST_COMMENTS, 3, 50),
        ("opinion-leader", Quest.QuestType.COMMENT_LIKES, 5, 25),
    )
    for code, qtype, target, reward in legacy:
        meta = QUEST_REGISTRY[code]
        Quest.objects.update_or_create(
            code=code,
            defaults={
                "title": meta["title"],
                "description": meta["description"],
                "quest_type": qtype,
                "target_count": target,
                "reward_tokens": reward,
            },
        )


def _pick_random_quest_code(exclude: set[str]) -> str:
    pool = [c for c in ALL_QUEST_CODES if c not in exclude]
    return random.choice(pool or ALL_QUEST_CODES)


def _assign_slot(slot: UserQuestSlot, quest_code: str) -> None:
    slot.quest_code = quest_code
    slot.progress = 0
    slot.extra_data = {}
    slot.completed_at = None
    slot.assigned_at = timezone.now()
    slot.save(
        update_fields=[
            "quest_code",
            "progress",
            "extra_data",
            "completed_at",
            "assigned_at",
        ]
    )


def refresh_user_quest_slots(user: User) -> None:
    now = timezone.now()
    cooldown = timedelta(days=QUEST_REFRESH_DAYS)
    slots = list(UserQuestSlot.objects.filter(user=user).order_by("slot"))
    by_slot = {s.slot: s for s in slots}
    existing_codes = {s.quest_code for s in slots}

    for slot_num in range(1, ACTIVE_SLOT_COUNT + 1):
        if slot_num not in by_slot:
            code = _pick_random_quest_code(existing_codes)
            existing_codes.add(code)
            UserQuestSlot.objects.create(
                user=user, slot=slot_num, quest_code=code
            )

    # Обновляем завершённые слоты (избегаем повторного запроса — используем уже загруженные)
    active_codes = {
        s.quest_code for s in slots if s.completed_at is None
    }
    for slot in slots:
        if slot.completed_at and now >= slot.completed_at + cooldown:
            _assign_slot(slot, _pick_random_quest_code(active_codes | {slot.quest_code}))
            # Обновляем active_codes: старый код выбыл, новый добавлен
            active_codes.discard(slot.quest_code)
            active_codes.add(slot.quest_code)


def _grant_slot_reward(user: User, quest_def: dict) -> None:
    if quest_def.get("free_post"):
        User.objects.filter(pk=user.pk).update(has_free_post=True)
        notify_quest_complete(user, quest_def["title"], free_post=True)
        return
    tokens = quest_def.get("reward_tokens", 0)
    if tokens:
        User.objects.filter(pk=user.pk).update(tokens=F("tokens") + tokens)
    notify_quest_complete(user, quest_def["title"], tokens)


def _complete_slot(slot: UserQuestSlot) -> None:
    if slot.completed_at:
        return
    quest_def = QUEST_REGISTRY[slot.quest_code]
    slot.progress = quest_def["target"]
    slot.completed_at = timezone.now()
    slot.save(update_fields=["progress", "completed_at"])
    _grant_slot_reward(slot.user, quest_def)


def _active_slot(user: User, quest_code: str) -> UserQuestSlot | None:
    refresh_user_quest_slots(user)
    return UserQuestSlot.objects.filter(
        user=user,
        quest_code=quest_code,
        completed_at__isnull=True,
    ).first()


def _set_slot_progress(slot: UserQuestSlot, value: int) -> None:
    quest_def = QUEST_REGISTRY[slot.quest_code]
    target = quest_def["target"]
    if value <= slot.progress:
        return
    slot.progress = min(value, target)
    slot.save(update_fields=["progress"])
    if slot.progress >= target:
        _complete_slot(slot)


def _max_post_likes_for_author(author_id: int) -> int:
    """Максимальное количество лайков на одном посте автора.
    Использует Subquery вместо материализации списка post_ids."""
    post_ct = ContentType.objects.get_for_model(Post)
    counts = (
        Like.objects.filter(
            content_type=post_ct,
            object_id__in=Post.objects.filter(author_id=author_id).values("pk"),
            is_active=True,
        )
        .values("object_id")
        .annotate(c=Count("id"))
        .values_list("c", flat=True)
    )
    return max(counts, default=0)


def _max_distinct_commenters_on_author_posts(author_id: int) -> int:
    """Максимальное количество уникальных комментаторов на одном посте автора.
    Раньше был N+1 (цикл по постам с отдельным запросом для каждого).
    Теперь — один запрос с GROUP BY."""
    counts = (
        Comment.objects.filter(
            post__author_id=author_id,
            is_active=True,
            parent__isnull=True,
        )
        .values("post_id")
        .annotate(cnt=Count("author_id", distinct=True))
        .values_list("cnt", flat=True)
    )
    return max(counts, default=0)


def _max_comment_likes_for_author(author_id: int) -> int:
    comment_ct = ContentType.objects.get_for_model(Comment)
    comment_ids = list(
        Comment.objects.filter(author_id=author_id).values_list("pk", flat=True)
    )
    if not comment_ids:
        return 0
    counts = (
        Like.objects.filter(
            content_type=comment_ct,
            object_id__in=comment_ids,
            is_active=True,
        )
        .values("object_id")
        .annotate(c=Count("id"))
        .values_list("c", flat=True)
    )
    return max(counts, default=0)


def check_post_like_quests(post: Post) -> None:
    slot = _active_slot(post.author, "content-star")
    if slot:
        _set_slot_progress(slot, _max_post_likes_for_author(post.author_id))


def check_post_comment_quests(post: Post) -> None:
    slot = _active_slot(post.author, "discussion")
    if slot:
        _set_slot_progress(
            slot, _max_distinct_commenters_on_author_posts(post.author_id)
        )


def check_comment_like_quests(comment: Comment) -> None:
    slot = _active_slot(comment.author, "opinion-leader")
    if slot:
        _set_slot_progress(slot, _max_comment_likes_for_author(comment.author_id))


def on_golden_post_liked(user: User, post_id: int) -> None:
    if not user.is_authenticated:
        return
    with transaction.atomic():
        slot = _active_slot(user, "golden_likes")
        if not slot:
            return
        ids = list(slot.extra_data.get("golden_liked_post_ids", []))
        if post_id in ids:
            return
        ids.append(post_id)
        slot.extra_data["golden_liked_post_ids"] = ids
        slot.save(update_fields=["extra_data"])
        _set_slot_progress(slot, len(ids))


def on_golden_comment_approved(comment_author: User) -> None:
    with transaction.atomic():
        slot = _active_slot(comment_author, "golden_approval")
        if slot:
            _set_slot_progress(slot, 1)


def on_post_life_extended(user: User, post_id: int, hours_remaining_before: float) -> None:
    if hours_remaining_before >= 24:
        return
    with transaction.atomic():
        slot = _active_slot(user, "dying_extensions")
        if not slot:
            return
        ids = list(slot.extra_data.get("dying_extended_post_ids", []))
        if post_id in ids:
            return
        ids.append(post_id)
        slot.extra_data["dying_extended_post_ids"] = ids
        slot.save(update_fields=["extra_data"])
        _set_slot_progress(slot, len(ids))


def get_user_quests_context(user: User) -> dict:
    refresh_user_quest_slots(user)
    items = []
    for slot in UserQuestSlot.objects.filter(user=user).order_by("slot"):
        quest_def = QUEST_REGISTRY.get(slot.quest_code)
        if not quest_def:
            continue
        completed = bool(slot.completed_at)
        available_at = None
        if completed:
            available_at = slot.completed_at + timedelta(days=QUEST_REFRESH_DAYS)
        items.append(
            {
                "title": quest_def["title"],
                "description": quest_def["description"],
                "progress": slot.progress,
                "target": quest_def["target"],
                "reward_label": quest_def.get("reward_label", ""),
                "completed": completed,
                "available_at": available_at,
            }
        )
    return {"quest_items": items}
