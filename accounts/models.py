from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


def default_vitality_expires():
    return timezone.now() + timedelta(days=180)


class User(AbstractUser):
    tokens = models.PositiveIntegerField(default=0)
    vitality_expires_at = models.DateTimeField(default=default_vitality_expires)
    login_streak = models.PositiveSmallIntegerField(default=0)
    last_streak_claim = models.DateField(null=True, blank=True)
    has_free_post = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.tokens = self.tokens + 50
        super().save(*args, **kwargs)


class Quest(models.Model):
    class QuestType(models.TextChoices):
        POST_LIKES = "post_likes", "Звезда контента"
        POST_COMMENTS = "post_comments", "Дискуссия"
        COMMENT_LIKES = "comment_likes", "Лидер мнений"

    code = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=128)
    description = models.TextField()
    quest_type = models.CharField(max_length=32, choices=QuestType.choices)
    target_count = models.PositiveSmallIntegerField()
    reward_tokens = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return self.title


class UserQuestProgress(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="quest_progress",
    )
    quest = models.ForeignKey(
        Quest,
        on_delete=models.CASCADE,
        related_name="user_progress",
    )
    progress = models.PositiveSmallIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "quest"),
                name="uniq_user_quest",
            )
        ]


class Notification(models.Model):
    class Kind(models.TextChoices):
        POST_LIKED = "post_liked", "Лайк поста"
        POST_DYING = "post_dying", "Пост умирает"
        QUEST_COMPLETE = "quest_complete", "Квест выполнен"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
