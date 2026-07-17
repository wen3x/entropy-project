from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .utils import generate_post_slug


def default_post_expires():
    return timezone.now() + timedelta(days=7)


def default_golden_expires():
    return timezone.now() + timedelta(hours=24)


def default_comment_expires():
    return timezone.now() + timedelta(hours=24)


class Post(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    slug = models.CharField(max_length=11, unique=True, db_index=True, blank=True)
    title = models.CharField(max_length=50)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_post_expires)
    is_active = models.BooleanField(default=True, db_index=True)
    is_golden = models.BooleanField(default=False, db_index=True)
    is_pinned = models.BooleanField(default=False, db_index=True)
    likes = GenericRelation("forum.Like")

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_post_slug()
        if self.is_golden and not self.pk:
            self.expires_at = default_golden_expires()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("forum:post_detail", args=[self.slug])


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_comment_expires)
    is_active = models.BooleanField(default=True, db_index=True)
    is_approved = models.BooleanField(default=False)
    approval_reward_paid = models.BooleanField(default=False)
    likes = GenericRelation("forum.Like")

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("post", "author"),
                condition=models.Q(parent__isnull=True),
                name="uniq_top_level_comment_per_user_post",
            )
        ]

    @property
    def is_reply(self):
        return self.parent_id is not None


class Like(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="likes_given",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, db_index=True)
    granted_time_extension = models.BooleanField(default=False)
    granted_golden_reward = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "content_type", "object_id"),
                name="uniq_like_per_user_target",
            )
        ]
        indexes = [
            models.Index(fields=("content_type", "object_id")),
        ]
