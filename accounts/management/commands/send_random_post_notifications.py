import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import NodeSubscription, Notification
from accounts.notifications import notify
from forum.models import Post


class Command(BaseCommand):
    help = "Рекомендует посты из отслеживаемых узлов (раз в 8–24ч)."

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

            # Активные посты в узле
            active_posts = Post.objects.filter(
                node=sub.node,
                is_active=True,
                expires_at__gt=now,
            )

            if not active_posts.exists():
                # Если в узле нет активных постов — пропускаем
                continue

            # Проверяем, какие посты из узла уже были отправлены пользователю
            all_post_urls = set(active_posts.values_list("slug", flat=True))
            already_notified = set(
                Notification.objects.filter(
                    user=sub.user,
                    kind=Notification.Kind.NODE_RANDOM_POST,
                ).values_list("link", flat=True)
            )
            # Извлекаем slug из ссылок вида "/p/slug/"
            notified_slugs = set()
            for link in already_notified:
                parts = link.strip("/").split("/")
                if parts:
                    notified_slugs.add(parts[-1])

            not_notified_slugs = all_post_urls - notified_slugs

            if not_notified_slugs:
                # Выбираем случайный пост, о котором ещё не уведомляли
                post = active_posts.filter(slug__in=not_notified_slugs).order_by("?").first()
                if post:
                    notify(
                        user=sub.user,
                        kind=Notification.Kind.NODE_RANDOM_POST,
                        message=f"Рекомендуем прочитать: {post.title}",
                        link=post.get_absolute_url(),
                    )
                    sent += 1
            else:
                # Все посты в узле уже были рекомендованы — пишем об узле
                node_url = sub.node.get_absolute_url()
                notify(
                    user=sub.user,
                    kind=Notification.Kind.NODE_INACTIVE,
                    message=f"В узле «{sub.node.name}» нет новых постов. Создайте свой!",
                    link=node_url,
                )
                sent += 1

            NodeSubscription.objects.filter(pk=sub.pk).update(
                last_notified_at=now,
            )

        self.stdout.write(self.style.SUCCESS(f"Отправлено {sent} уведомлений."))
