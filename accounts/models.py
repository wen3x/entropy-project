from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


def default_vitality_expires():
    return timezone.now() + timedelta(days=180)


class User(AbstractUser):
    class ProfileColor(models.TextChoices):
        DEFAULT = "", "По умолчанию"
        RED = "red", "Красный"
        BLUE = "blue", "Синий"
        GREEN = "green", "Зелёный"
        GOLD = "gold", "Золотой"
        ICE = "ice", "Ледяное сияние"
        MATRIX = "matrix", "Матрица"
        SUNSET = "sunset", "Закат энтропии"

    tokens = models.PositiveIntegerField(default=0)
    vitality_expires_at = models.DateTimeField(default=default_vitality_expires)
    login_streak = models.PositiveSmallIntegerField(default=0)
    last_streak_claim = models.DateField(null=True, blank=True)
    has_free_post = models.BooleanField(default=False)
    profile_color = models.CharField(
        max_length=16,
        choices=ProfileColor.choices,
        blank=True,
        default="",
    )
    has_basic_colors = models.BooleanField(default=False)
    has_gold_color = models.BooleanField(default=False)
    owned_colors = models.JSONField(default=list, blank=True)
    is_anonymous_mode = models.BooleanField(default=False, help_text="Анонимный режим: имя скрывается в постах и комментариях")

    @property
    def owned_colors_list(self):
        """Все купленные цвета профиля."""
        colors = list(self.owned_colors or [])
        # Миграция со старыми полями
        if self.has_basic_colors:
            for c in ("ice", "matrix", "sunset"):
                if c not in colors:
                    colors.append(c)
        if self.has_gold_color and "gold" not in colors:
            colors.append("gold")
        return colors

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


class UserQuestSlot(models.Model):
    """Три слота случайных квестов; после выполнения новый через 3 дня."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="quest_slots",
    )
    slot = models.PositiveSmallIntegerField()
    quest_code = models.CharField(max_length=64, db_index=True)
    progress = models.PositiveSmallIntegerField(default=0)
    extra_data = models.JSONField(default=dict, blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "slot"),
                name="uniq_user_quest_slot",
            )
        ]
        ordering = ("slot",)

    def __str__(self):
        return f"{self.user.username} slot {self.slot}: {self.quest_code}"


class UserDailyQuestCycle(models.Model):
    """Ежедневный цикл из 6 квестов; обновляется через 24ч после выполнения 3 любых."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="daily_quest_cycle",
    )
    cycle_started_at = models.DateTimeField(auto_now_add=True)
    cycle_completed_at = models.DateTimeField(null=True, blank=True)

    # Старые квесты
    golden_likes_done = models.BooleanField(default=False)
    golden_approval_done = models.BooleanField(default=False)
    dying_extensions_done = models.BooleanField(default=False)
    golden_liked_post_ids = models.JSONField(default=list, blank=True)
    dying_extended_post_ids = models.JSONField(default=list, blank=True)

    # Новые квесты
    comment_streak_done = models.BooleanField(default=False)
    post_and_earn_done = models.BooleanField(default=False)
    near_death_done = models.BooleanField(default=False)
    comment_streak_post_ids = models.JSONField(default=list, blank=True)
    post_and_earn_tracked_post_id = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"Daily quests — {self.user.username}"


class ShopItem(models.Model):
    class ItemType(models.TextChoices):
        EXTEND_VITALITY = "extend_vitality", "Продление жизни аккаунта"
        PROFILE_COLOR_BASIC = "profile_color_basic", "Базовый цвет профиля"
        PROFILE_COLOR_GOLD = "profile_color_gold", "Золотой цвет профиля"

    code = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=128)
    description = models.TextField()
    price_tokens = models.PositiveIntegerField()
    item_type = models.CharField(max_length=32, choices=ItemType.choices)
    visible_in_shop = models.BooleanField(default=False, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")

    def __str__(self):
        return self.title


class NodeSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="node_subscriptions",
    )
    node = models.ForeignKey(
        "forum.Node",
        on_delete=models.CASCADE,
        related_name="subscribers",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "node"),
                name="uniq_user_node_subscription",
            )
        ]

    def __str__(self):
        return f"{self.user.username} → {self.node.name}"


class Ban(models.Model):
    """Бан пользователя. Если node=None — глобальный бан (не может писать нигде).
    Если node задан — пользователь не может писать в этом узле."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bans",
    )
    node = models.ForeignKey(
        "forum.Node",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bans",
    )
    reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        target = "глобальный" if self.node is None else f"узел «{self.node.name}»"
        return f"Бан {self.user.username} ({target}) до {self.expires_at:%d.%m %H:%M}"


class Moderator(models.Model):
    """Модератор узла. Если node=None — модератор всего форума."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="moderations",
    )
    node = models.ForeignKey(
        "forum.Node",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="moderators",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_moderations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "node"),
                name="uniq_moderator_user_node",
            )
        ]
        ordering = ("-created_at",)

    def __str__(self):
        target = "весь форум" if self.node is None else f"узел «{self.node.name}»"
        return f"Модератор {self.user.username} ({target})"


class PushSubscription(models.Model):
    """Подписка браузера на Push-уведомления (Web Push Protocol)."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.URLField(max_length=500)
    p256dh = models.CharField(max_length=256)
    auth = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "endpoint"),
                name="uniq_user_push_endpoint",
            )
        ]

    def __str__(self):
        return f"Push sub: {self.user.username}"


class Notification(models.Model):
    class Kind(models.TextChoices):
        POST_LIKED = "post_liked", "Лайк поста"
        POST_DYING = "post_dying", "Пост умирает"
        QUEST_COMPLETE = "quest_complete", "Квест выполнен"
        NODE_RANDOM_POST = "node_random_post", "Рекомендация поста"
        NODE_INACTIVE = "node_inactive", "Узел без активности"
        NEW_COMMENT = "new_comment", "Новый комментарий"
        COMMENT_REPLY = "comment_reply", "Ответ на комментарий"
        MENTION = "mention", "Упоминание"
        BAN = "ban", "Бан"

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
