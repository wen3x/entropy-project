import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import F
from django.utils import timezone

from accounts.models import NodeSubscription, Notification
from forum.models import Post


class Command(BaseCommand):
    help = "Отправляет уведомления со случайными постами из отслеживаемых узлов (раз в 8–24ч)."

    def handle(self, *args, **options):
        now = timezone.now()
        sent = 0

        for sub in NodeSubscription.objects.select_related("user", "node").iterator():
            # Если никогда не уведомляли — пора
            if sub.last_notified_at is None:
                due = True
            else:
                # Интервал 8–24 часа (рандомно для каждой подписки)
                interval = timedelta(hours=random.uniform(8, 24))
                due = sub.last_notified_at + interval <= now

            if not due:
                continue

            # Выбираем случайный активный пост из узла
            posts = Post.objects.filter(
                node=sub.node,
                is_active=True,
                expires_at__gt=now,
            )
            post = posts.order_by("?").first()
            if not post:
                # Если в узле нет активных постов, пропускаем
                continue

            Notification.objects.create(
                user=sub.user,
                kind=Notification.Kind.NODE_RANDOM_POST,
                message=f"Случайный пост из «{sub.node.name}»: {post.title}",
                link=post.get_absolute_url(),
            )

            NodeSubscription.objects.filter(pk=sub.pk).update(
                last_notified_at=now,
            )
            sent += 1

        self.stdout.write(self.style.SUCCESS(f"Отправлено {sent} уведомлений."))
