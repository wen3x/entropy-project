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


class Node(models.Model):
    slug = models.SlugField(max_length=32, unique=True, db_index=True)
    name = models.CharField(max_length=64)
    description = models.TextField(blank=True, default="")
    # Cloudinary media for node
    avatar = models.CharField(max_length=1024, blank=True, default="")
    header = models.CharField(max_length=1024, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_nodes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("forum:node_detail", args=[self.slug])


class Post(models.Model):
    node = models.ForeignKey(
        Node,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    slug = models.CharField(max_length=11, unique=True, db_index=True, blank=True)
    title = models.CharField(max_length=50, blank=True, default="")
    content = models.TextField(blank=True, default="")
    # Cloudinary media
    image = models.CharField(max_length=1024, blank=True, default="")
    audio = models.CharField(max_length=1024, blank=True, default="")
    gif = models.CharField(max_length=1024, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_post_expires)
    is_active = models.BooleanField(default=True, db_index=True)
    is_golden = models.BooleanField(default=False, db_index=True)
    is_pinned = models.BooleanField(default=False, db_index=True)
    likes = GenericRelation("forum.Like")

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title or f"Пост #{self.pk}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_post_slug()
        if self.is_golden and not self.pk:
            self.expires_at = default_golden_expires()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        if self.node_id:
            return reverse("forum:post_detail_in_node", args=[self.node.slug, self.slug])
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
    # Cloudinary media
    image = models.CharField(max_length=1024, blank=True, default="")
    gif = models.CharField(max_length=1024, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(default=default_comment_expires)
    is_active = models.BooleanField(default=True, db_index=True)
    is_approved = models.BooleanField(default=False)
    approval_reward_paid = models.BooleanField(default=False)
    likes = GenericRelation("forum.Like")

    class Meta:
        ordering = ("created_at",)

    @property
    def is_reply(self):
        return self.parent_id is not None

    @property
    def is_edited(self):
        return self.edited_at is not None


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
