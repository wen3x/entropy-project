import random
from datetime import timedelta
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import NodeSubscription, Notification
from accounts.notifications import notify
from forum.models import Post


class Command(BaseCommand):
    help = "Рекомендует пост из одного случайного узла раз в 8–24ч на пользователя."

    def handle(self, *args, **options):
        now = timezone.now()
        sent = 0

        # Группируем подписки по пользователю, выбираем те, что пора уведомлять
        user_subs = defaultdict(list)
        for sub in NodeSubscription.objects.select_related("user", "node").iterator():
            if sub.last_notified_at is None:
                due = True
            else:
                interval = timedelta(hours=random.uniform(8, 24))
                due = sub.last_notified_at + interval <= now

            if not due:
                continue
            user_subs[sub.user_id].append(sub)

        for user_id, subs in user_subs.items():
            # Выбираем один случайный узел из тех, что пора уведомлять
            random.shuffle(subs)
            chosen_sub = None

            for sub in subs:
                has_active = Post.objects.filter(
                    node=sub.node,
                    is_active=True,
                    expires_at__gt=now,
                ).exists()
                if has_active:
                    chosen_sub = sub
                    break

            if not chosen_sub:
                chosen_sub = subs[0]

            user_obj = chosen_sub.user

            # Активные посты в выбранном узле
            active_posts = Post.objects.filter(
                node=chosen_sub.node,
                is_active=True,
                expires_at__gt=now,
            )

            if active_posts.exists():
                # Проверяем, какие посты уже отправляли
                already_notified = set(
                    Notification.objects.filter(
                        user=user_obj,
                        kind=Notification.Kind.NODE_RANDOM_POST,
                    ).values_list("link", flat=True)
                )
                notified_slugs = set()
                for link in already_notified:
                    parts = link.strip("/").split("/")
                    if parts:
                        notified_slugs.add(parts[-1])

                all_slugs = set(active_posts.values_list("slug", flat=True))
                not_notified = all_slugs - notified_slugs

                if not_notified:
                    post = active_posts.filter(slug__in=not_notified).order_by("?").first()
                else:
                    post = active_posts.order_by("?").first()

                if post:
                    notify(
                        user=user_obj,
                        kind=Notification.Kind.NODE_RANDOM_POST,
                        message=f"Рекомендуем прочитать: {post.title}",
                        link=post.get_absolute_url(),
                    )
                    sent += 1
            else:
                node_url = chosen_sub.node.get_absolute_url()
                notify(
                    user=user_obj,
                    kind=Notification.Kind.NODE_INACTIVE,
                    message=f"В узле «{chosen_sub.node.name}» нет новых постов. Создайте свой!",
                    link=node_url,
                )
                sent += 1

            # Обновляем last_notified_at для ВСЕХ подписок пользователя
            NodeSubscription.objects.filter(user_id=user_id).update(
                last_notified_at=now,
            )

        self.stdout.write(self.style.SUCCESS(f"Отправлено {sent} уведомлений."))
