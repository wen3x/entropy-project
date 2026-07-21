from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    Complaint,
    Moderator,
    Notification,
    PushSubscription,
    Quest,
    ShopItem,
    User,
    UserDailyQuestCycle,
    UserQuestProgress,
    UserQuestSlot,
)


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "endpoint", "created_at")
    list_filter = ("created_at",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "is_read", "created_at")
    list_filter = ("kind", "is_read")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Entropy",
            {
                "fields": (
                    "tokens",
                    "vitality_expires_at",
                    "login_streak",
                    "last_streak_claim",
                    "free_posts",
                    "profile_color",
                )
            },
        ),
    )
    list_display = (
        "username",
        "email",
        "tokens",
        "login_streak",
        "vitality_expires_at",
        "free_posts",
        "is_staff",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "free_posts")


@admin.register(Quest)
class QuestAdmin(admin.ModelAdmin):
    list_display = ("title", "code", "target_count", "reward_tokens", "is_active")
    search_fields = ("title", "code")


@admin.register(UserQuestProgress)
class UserQuestProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "quest", "progress", "completed_at")
    list_filter = ("quest",)


@admin.register(ShopItem)
class ShopItemAdmin(admin.ModelAdmin):
    list_display = ("title", "code", "price_tokens", "visible_in_shop", "sort_order")
    list_filter = ("visible_in_shop", "item_type")
    list_editable = ("visible_in_shop", "sort_order")


@admin.register(UserQuestSlot)
class UserQuestSlotAdmin(admin.ModelAdmin):
    list_display = ("user", "slot", "quest_code", "progress", "completed_at")
    list_filter = ("quest_code", "completed_at")


@admin.register(Moderator)
class ModeratorAdmin(admin.ModelAdmin):
    list_display = ("user", "node", "created_by", "created_at")
    list_filter = ("node",)
    search_fields = ("user__username",)


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ("reporter", "reason", "status", "content_type", "created_at")
    list_filter = ("status", "reason")
    search_fields = ("reporter__username", "message")


@admin.register(UserDailyQuestCycle)
class UserDailyQuestCycleAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "cycle_started_at",
        "cycle_completed_at",
        "golden_likes_done",
        "golden_approval_done",
        "dying_extensions_done",
    )
