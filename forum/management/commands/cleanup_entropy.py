from django.core.management.base import BaseCommand
from django.utils import timezone

from forum.models import Comment, Post


class Command(BaseCommand):
    help = "Жнец: помечает expired Post и Comment как неактивные (архив), без физического удаления постов."

    def handle(self, *args, **options):
        now = timezone.now()
        posts = Post.objects.filter(expires_at__lt=now, is_active=True)
        posts_count = posts.update(is_active=False)
        comments = Comment.objects.filter(expires_at__lt=now, is_active=True)
        comments_count = comments.update(is_active=False)
        self.stdout.write(
            self.style.SUCCESS(
                f"[cleanup_entropy] {now.isoformat()} — архив постов: {posts_count}, "
                f"архив комментариев: {comments_count}"
            )
        )
