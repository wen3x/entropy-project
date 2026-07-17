from django.core.management.base import BaseCommand
from django.db.models import Q

from forum.models import Post
from forum.utils import generate_post_slug


class Command(BaseCommand):
    help = "Генерирует уникальные slug для постов без кода (миграция на новые URL)."

    def handle(self, *args, **options):
        posts = Post.objects.filter(Q(slug="") | Q(slug__isnull=True))
        count = 0
        for post in posts.iterator():
            post.slug = generate_post_slug()
            post.save(update_fields=["slug"])
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Обновлено постов: {count}"))
