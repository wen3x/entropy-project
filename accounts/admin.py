from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Notification, Quest, User, UserQuestProgress


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
                    "has_free_post",
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
        "has_free_post",
        "is_staff",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "has_free_post")


@admin.register(Quest)
class QuestAdmin(admin.ModelAdmin):
    list_display = ("title", "code", "target_count", "reward_tokens", "is_active")
    search_fields = ("title", "code")


@admin.register(UserQuestProgress)
class UserQuestProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "quest", "progress", "completed_at")
    list_filter = ("quest",)
