from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, F
from django.utils import timezone

from forum.models import Comment, Like, Post

from .models import Quest, User, UserQuestProgress

QUEST_RESET_DAYS = 3

DEFAULT_QUESTS = (
    {
        "code": "content-star",
        "title": "Звезда контента",
        "description": "Соберите 5 лайков на одном своём посте.",
        "quest_type": Quest.QuestType.POST_LIKES,
        "target_count": 5,
        "reward_tokens": 40,
    },
    {
        "code": "discussion",
        "title": "Дискуссия",
        "description": "Получите 3 комментария от разных пользователей под одним своим постом.",
        "quest_type": Quest.QuestType.POST_COMMENTS,
        "target_count": 3,
        "reward_tokens": 50,
    },
    {
        "code": "opinion-leader",
        "title": "Лидер мнений",
        "description": "Соберите 5 лайков на одном своём комментарии.",
        "quest_type": Quest.QuestType.COMMENT_LIKES,
        "target_count": 5,
        "reward_tokens": 25,
    },
)


def ensure_default_quests():
    for data in DEFAULT_QUESTS:
        Quest.objects.update_or_create(code=data["code"], defaults=data)


def _reset_if_elapsed(progress: UserQuestProgress) -> UserQuestProgress:
    if not progress.completed_at:
        return progress
    if progress.completed_at + timedelta(days=QUEST_RESET_DAYS) <= timezone.now():
        progress.progress = 0
        progress.completed_at = None
        progress.save(update_fields=["progress", "completed_at"])
    return progress


def _get_or_create_progress(user: User, quest: Quest) -> UserQuestProgress:
    progress, _ = UserQuestProgress.objects.get_or_create(user=user, quest=quest)
    return _reset_if_elapsed(progress)


def _complete_quest(progress: UserQuestProgress) -> None:
    if progress.completed_at:
        return
    progress.completed_at = timezone.now()
    progress.progress = progress.quest.target_count
    progress.save(update_fields=["completed_at", "progress"])
    User.objects.filter(pk=progress.user_id).update(
        tokens=F("tokens") + progress.quest.reward_tokens
    )
    from accounts.notifications import notify_quest_complete

    notify_quest_complete(
        progress.user,
        progress.quest.title,
        progress.quest.reward_tokens,
    )


def _update_progress(user: User, quest_code: str, value: int) -> None:
    try:
        quest = Quest.objects.get(code=quest_code, is_active=True)
    except Quest.DoesNotExist:
        return

    progress = _get_or_create_progress(user, quest)
    if progress.completed_at:
        return

    if value > progress.progress:
        progress.progress = min(value, quest.target_count)
        progress.save(update_fields=["progress"])
        if progress.progress >= quest.target_count:
            _complete_quest(progress)


def _max_post_likes_for_author(author_id: int) -> int:
    post_ct = ContentType.objects.get_for_model(Post)
    post_ids = list(Post.objects.filter(author_id=author_id).values_list("pk", flat=True))
    if not post_ids:
        return 0
    counts = (
        Like.objects.filter(
            content_type=post_ct,
            object_id__in=post_ids,
            is_active=True,
        )
        .values("object_id")
        .annotate(c=Count("id"))
        .values_list("c", flat=True)
    )
    return max(counts, default=0)


def _max_distinct_commenters_on_author_posts(author_id: int) -> int:
    best = 0
    for post in Post.objects.filter(author_id=author_id).only("pk"):
        distinct = (
            post.comments.filter(is_active=True, parent__isnull=True)
            .values("author_id")
            .distinct()
            .count()
        )
        best = max(best, distinct)
    return best


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
    _update_progress(post.author, "content-star", _max_post_likes_for_author(post.author_id))


def check_post_comment_quests(post: Post) -> None:
    _update_progress(
        post.author,
        "discussion",
        _max_distinct_commenters_on_author_posts(post.author_id),
    )


def check_comment_like_quests(comment: Comment) -> None:
    _update_progress(
        comment.author,
        "opinion-leader",
        _max_comment_likes_for_author(comment.author_id),
    )


def get_user_quests_context(user: User) -> list[dict]:
    ensure_default_quests()
    quests = Quest.objects.filter(is_active=True)
    progress_map = {
        p.quest_id: _reset_if_elapsed(p)
        for p in UserQuestProgress.objects.filter(user=user, quest__in=quests)
    }
    items = []
    for quest in quests:
        progress = progress_map.get(quest.pk)
        if progress is None:
            progress = UserQuestProgress.objects.create(user=user, quest=quest)
        completed = bool(progress.completed_at)
        available_at = None
        if completed:
            available_at = progress.completed_at + timedelta(days=QUEST_RESET_DAYS)
        items.append(
            {
                "quest": quest,
                "progress": progress.progress,
                "target": quest.target_count,
                "completed": completed,
                "available_at": available_at,
                "reward": quest.reward_tokens,
            }
        )
    return items
