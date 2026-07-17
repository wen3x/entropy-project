from datetime import timedelta

from django.utils import timezone

from .models import Notification, User


def notify(user: User, kind: str, message: str, link: str = "") -> Notification:
    return Notification.objects.create(
        user=user,
        kind=kind,
        message=message,
        link=link,
    )


def notify_post_liked(post_author: User, liker_username: str, post_title: str, post_url: str):
    if post_author.username == liker_username:
        return
    notify(
        post_author,
        Notification.Kind.POST_LIKED,
        f"«{post_title}» понравился пользователю {liker_username}.",
        link=post_url,
    )


def notify_quest_complete(user: User, quest_title: str, reward: int = 0, *, free_post: bool = False):
    if free_post:
        message = f"Квест «{quest_title}» выполнен! Право на бесплатный пост."
    elif reward:
        message = f"Квест «{quest_title}» выполнен! +{reward} токенов."
    else:
        message = f"Квест «{quest_title}» выполнен!"
    notify(
        user,
        Notification.Kind.QUEST_COMPLETE,
        message,
        link="/accounts/profile/",
    )


def notify_post_dying(user: User, post_title: str, post_url: str):
    """Не чаще одного уведомления на пост за последние 2 часа."""
    since = timezone.now() - timedelta(hours=2)
    exists = Notification.objects.filter(
        user=user,
        kind=Notification.Kind.POST_DYING,
        message__contains=post_title[:50],
        created_at__gte=since,
    ).exists()
    if exists:
        return
    notify(
        user,
        Notification.Kind.POST_DYING,
        f"Пост «{post_title}» умрёт менее чем через 2 часа!",
        link=post_url,
    )


def check_dying_posts_for_user(user: User):
    from forum.models import Post

    now = timezone.now()
    threshold = now + timedelta(hours=2)
    posts = Post.objects.filter(
        author=user,
        is_active=True,
        expires_at__gt=now,
        expires_at__lte=threshold,
        is_golden=False,
    )
    for post in posts:
        notify_post_dying(user, post.title, post.get_absolute_url())
