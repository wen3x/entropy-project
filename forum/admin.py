from django.contrib import admin

from .models import Comment, Like, Post


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    fk_name = "post"


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "author", "is_golden", "is_active", "expires_at")
    list_filter = ("is_golden", "is_active", "created_at")
    search_fields = ("title", "slug", "content")
    readonly_fields = ("slug",)
    inlines = [CommentInline]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("post", "author", "parent", "is_approved", "created_at", "is_active")
    list_filter = ("is_active", "is_approved")
    search_fields = ("text",)


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "content_type",
        "object_id",
        "is_active",
        "granted_golden_reward",
        "created_at",
    )
    list_filter = ("content_type", "is_active")
