import base64
import json
import logging
from datetime import timedelta
from functools import lru_cache
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from .models import Notification, PushSubscription, User

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_vapid() -> Vapid:
    """Создать Vapid instance из raw base64-ключа (32 байта) в настройках."""
    key_b64 = settings.WEBPUSH_VAPID_PRIVATE_KEY
    padding = 4 - len(key_b64) % 4
    if padding != 4:
        key_b64 += "=" * padding
    priv_bytes = base64.urlsafe_b64decode(key_b64)
    private_value = int.from_bytes(priv_bytes, "big")
    private_key = ec.derive_private_key(
        private_value, ec.SECP256R1(), default_backend()
    )
    return Vapid(private_key=private_key)


def _send_web_push(user: User, title: str, body: str, icon: str = "", url: str = ""):
    """Отправить push-уведомление на все подписки пользователя."""
    subs = PushSubscription.objects.filter(user=user)
    if not subs.exists():
        return

    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": icon or "/static/img/favicon.png",
        "badge": "/static/img/favicon.png",
        "data": {"url": url},
    })

    try:
        vapid = _get_vapid()
    except Exception as e:
        logger.warning(f"Не удалось загрузить VAPID ключ: {e}")
        return

    for sub in subs:
        try:
            # Динамически определяем aud из endpoint (нужно для Google FCM)
            parsed = urlparse(sub.endpoint)
            claims = {
                **settings.WEBPUSH_VAPID_CLAIMS,
                "aud": f"{parsed.scheme}://{parsed.netloc}",
            }
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.p256dh,
                        "auth": sub.auth,
                    },
                },
                data=payload,
                vapid_private_key=vapid,
                vapid_claims=claims,
            )
        except WebPushException as e:
            # Если подписка истекла/невалидна — удаляем её
            if e.response and e.response.status_code in (401, 404, 410):
                sub.delete()
                logger.info(f"Удалена просроченная push-подписка {sub.pk} для {user.username}")
            else:
                logger.warning(f"Push-ошибка для {user.username}: {e}")
        except Exception as e:
            logger.warning(f"Push-ошибка для {user.username}: {e}")


def notify(user: User, kind: str, message: str, link: str = "") -> Notification:
    note = Notification.objects.create(
        user=user,
        kind=kind,
        message=message,
        link=link,
    )
    # Отправляем push-уведомление
    _send_web_push(
        user=user,
        title="Entropy",
        body=message,
        url=link,
    )
    return note


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
