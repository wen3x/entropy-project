import logging

import django.db.utils

from django.contrib import messages
from django.contrib.auth import logout
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .streaks import process_daily_login

logger = logging.getLogger(__name__)


def vitality_exempt_paths():
    login_path = reverse("login")
    register_path = reverse("register")
    expired_path = reverse("vitality_expired")
    return frozenset({login_path, register_path, expired_path})


class VitalityMiddleware:
    """Проверяет vitality_expires_at; истёкший аккаунт выходит из сессии."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._exempt = vitality_exempt_paths()

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and request.path not in self._exempt
            and request.user.vitality_expires_at <= timezone.now()
        ):
            logout(request)
            return redirect(reverse("vitality_expired"))

        return self.get_response(request)


class BanMiddleware:
    """Перехватывает POST-запросы на создание контента и проверяет бан.
    Если пользователь забанен — показывает сообщение и редиректит обратно.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return None
        if request.method != "POST":
            return None

        url_name = getattr(request.resolver_match, "url_name", None)
        username = request.user.username
        path = request.path

        logger.info(
            f"BanMiddleware: {username} POST -> {path} (url_name={url_name})"
        )

        # ── Создание нового поста ──
        if url_name in ("post_create", "post_create_in_node"):
            # Определяем целевой узел
            node_slug = view_kwargs.get("node_slug")
            target_node = None
            if node_slug:
                target_node = self._resolve_node(node_slug)
            else:
                target_node = self._resolve_node("global")

            # Проверяем глобальный бан (Python — ловит битые FK)
            if self._is_banned(request.user):
                logger.warning(
                    f"BanMiddleware: ЗАБЛОКИРОВАН {username} "
                    f"(глобальный бан)"
                )
                messages.error(
                    request, "Вы забанены и не можете создавать посты."
                )
                return redirect("forum:post_list")

            # Проверяем узел-специфичный бан (SQL — для существующих узлов)
            if target_node and self._is_banned(request.user, target_node):
                logger.warning(
                    f"BanMiddleware: ЗАБЛОКИРОВАН {username} "
                    f"в узле {node_slug or 'global'}"
                )
                messages.error(
                    request,
                    "Вы забанены в этом узле и не можете создавать здесь посты.",
                )
                return redirect(
                    "forum:node_detail",
                    node_slug=node_slug or "global",
                )

        # ── Быстрая публикация медиа в узле ──
        elif url_name == "node_detail":
            action = request.POST.get("action")
            if action == "quick_media_post":
                node_slug = view_kwargs.get("node_slug")
                node = self._resolve_node(node_slug)
                if node:
                    is_b = self._is_banned(request.user, node)
                    logger.info(
                        f"BanMiddleware: quick_media {username} в "
                        f"{node_slug}, banned={is_b}"
                    )
                    if is_b:
                        messages.error(
                            request,
                            "Вы забанены и не можете писать в этом узле.",
                        )
                        return redirect(
                            "forum:node_detail", node_slug=node_slug
                        )

        # ── Комментарий к посту (без node_slug в URL) ──
        elif url_name == "post_detail":
            slug = view_kwargs.get("slug")
            post = self._resolve_post(slug)
            if post:
                is_b = self._is_banned(request.user, post.node)
                logger.info(
                    f"BanMiddleware: comment {username} на пост "
                    f"{slug} (node={post.node.slug if post.node else 'None'}), "
                    f"banned={is_b}"
                )
                if is_b:
                    messages.error(
                        request, "Вы забанены и не можете комментировать."
                    )
                    return redirect("forum:post_detail", slug=slug)

        # ── Комментарий внутри узла ──
        elif url_name == "post_detail_in_node":
            post_slug = view_kwargs.get("post_slug")
            node_slug = view_kwargs.get("node_slug")
            post = self._resolve_post(post_slug)
            if post:
                is_b = self._is_banned(request.user, post.node)
                logger.info(
                    f"BanMiddleware: comment_in_node {username} -> "
                    f"{node_slug}/{post_slug}, banned={is_b}"
                )
                if is_b:
                    messages.error(
                        request, "Вы забанены и не можете комментировать."
                    )
                    return redirect(
                        "forum:post_detail_in_node",
                        node_slug=node_slug,
                        post_slug=post_slug,
                    )

        # ── Редактирование комментария ──
        elif url_name == "edit_comment":
            pk = view_kwargs.get("pk")
            comment = self._resolve_comment(pk)
            if comment:
                is_b = self._is_banned(request.user, comment.post.node)
                logger.info(
                    f"BanMiddleware: edit_comment {username} pk={pk}, "
                    f"banned={is_b}"
                )
                if is_b:
                    messages.error(
                        request,
                        "Вы забанены и не можете редактировать комментарии.",
                    )
                    return redirect(comment.post.get_absolute_url())

        return None

    # ── Helpers ──────────────────────────────────────────────────────

    def _is_banned(self, user, node=None):
        """Проверить, есть ли активный бан у пользователя."""
        try:
            from accounts.models import Ban

            now = timezone.now()
            if node:
                return Ban.objects.filter(
                    user=user, expires_at__gt=now
                ).filter(
                    Q(node=node) | Q(node__isnull=True)
                ).exists()
            # Глобальный бан: проверяем Python'ом, иначе битые FK не ловятся
            for ban in Ban.objects.filter(
                user=user, expires_at__gt=now
            ).select_related('node')[:100]:
                if ban.node is None:
                    return True
            return False
        except (django.db.utils.OperationalError, django.db.utils.ProgrammingError):
            return False

    def _resolve_node(self, slug):
        from forum.models import Node
        try:
            return Node.objects.get(slug=slug, is_active=True)
        except Node.DoesNotExist:
            return None

    def _resolve_post(self, slug):
        from forum.models import Post
        try:
            return Post.objects.select_related("node").get(slug=slug)
        except Post.DoesNotExist:
            return None

    def _resolve_comment(self, pk):
        from forum.models import Comment
        try:
            return Comment.objects.select_related("post__node").get(pk=pk)
        except Comment.DoesNotExist:
            return None


class DailyStreakMiddleware:
    """Один раз в день обновляет стрик и начисляет награду при активности пользователя."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._exempt = vitality_exempt_paths()

    def __call__(self, request):
        if request.user.is_authenticated and request.path not in self._exempt:
            summary = process_daily_login(request.user)
            if summary:
                request.session["streak_reward"] = summary
                request.user.refresh_from_db()
                day = summary["streak_day"]
                reward = summary["tokens_reward"]
                if summary["has_free_post"]:
                    messages.success(
                        request,
                        f"День {day} стрика! Вы получили право на один бесплатный пост.",
                    )
                elif reward:
                    messages.success(
                        request,
                        f"День {day} стрика: +{reward} токенов.",
                    )
                else:
                    messages.info(request, f"День {day} стрика. Продолжайте завтра!")

        return self.get_response(request)


class OnlineUsersMiddleware:
    """Пишет в сессию last_ping для счётчика онлайн."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._admin_prefix = reverse("admin:index")

    def __call__(self, request):
        if not request.path.startswith(self._admin_prefix) and request.user.is_authenticated:
            request.session["last_ping"] = timezone.now().timestamp()
        return self.get_response(request)
