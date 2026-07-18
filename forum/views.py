from pathlib import Path
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count, F, Q
import django.db.utils
from django.http import Http404, HttpResponse, HttpResponseForbidden, HttpResponseGone, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.models import Ban, NodeSubscription
from accounts.notifications import (
    check_dying_posts_for_user,
    notify,
)
from accounts.quests import (
    check_comment_like_quests,
    check_post_comment_quests,
    check_post_like_quests,
    get_user_quests_context,
    on_golden_comment_approved,
    on_golden_post_liked,
    on_post_life_extended,
)

from .forms import CommentForm, NodeForm, PostForm
from .models import Comment, Like, Node, Post
from .rate_limit import allow_like, deny_like_message

POST_CREATION_COST = 25
ACTIVE_LIKE = Q(likes__is_active=True)
GOLDEN_LIKE_REWARD = 10
APPROVAL_REWARD = 100


import re
from django.contrib.auth import get_user_model as get_user_model_func


def notify_mentions(text, from_user, link=""):
    """Найти @username в тексте и отправить уведомление."""
    if not text:
        return
    User = get_user_model_func()
    for match in re.finditer(r"@(\w+)", text):
        username = match.group(1)
        try:
            mentioned = User.objects.get(username__iexact=username)
            if mentioned.pk != from_user.pk:
                notify(
                    mentioned,
                    "mention",
                    f"@{from_user.username} упомянул вас в своём посте.",
                    link=link,
                )
        except User.DoesNotExist:
            pass


def upload_to_cloudinary(file_obj, resource_type="auto"):
    """Загрузить файл в Cloudinary, вернуть secure_url или пустую строку."""
    if not file_obj:
        return None
    try:
        import cloudinary.uploader
        result = cloudinary.uploader.upload(file_obj, resource_type=resource_type)
        return result.get("secure_url", "")
    except ImportError:
        # Cloudinary не установлен
        return None
    except Exception:
        # Любая ошибка Cloudinary
        return None


def is_god(user) -> bool:
    return user.is_authenticated and user.username == "wen3x"


def is_banned(user, node=None) -> bool:
    """Проверить, забанен ли пользователь.
    Если node указан — проверяет бан только для этого узла.
    Если node=None — проверяет глобальный бан.
    Если таблица банов не существует — безопасно возвращает False."""
    if not user.is_authenticated:
        return False
    try:
        now = timezone.now()
        if node:
            return Ban.objects.filter(
                user=user, expires_at__gt=now
            ).filter(
                Q(node=node) | Q(node__isnull=True)
            ).exists()
        # Глобальный бан: проверяем на уровне Python, т.к. SQL не ловит
        # битые FK (node удалён, но node_id != NULL).
        for ban in Ban.objects.filter(
            user=user, expires_at__gt=now
        ).select_related('node')[:100]:
            if ban.node is None:
                return True
        return False
    except (django.db.utils.OperationalError, django.db.utils.ProgrammingError):
        # Таблица может не существовать (миграция не применилась)
        return False


def wants_json(request) -> bool:
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept


def json_like_error(request, message: str, status: int = 429):
    if wants_json(request):
        return JsonResponse({"ok": False, "error": message}, status=status)
    messages.error(request, message)
    return redirect(request.META.get("HTTP_REFERER", "/"))


def post_like_count(post: Post) -> int:
    post_ct = ContentType.objects.get_for_model(Post)
    return Like.objects.filter(
        content_type=post_ct, object_id=post.pk, is_active=True
    ).count()


def comment_like_count(comment: Comment) -> int:
    comment_ct = ContentType.objects.get_for_model(Comment)
    return Like.objects.filter(
        content_type=comment_ct, object_id=comment.pk, is_active=True
    ).count()


def extend_post_on_comment(post: Post, user) -> bool:
    """Продлевает жизнь поста, только если это первый комментарий пользователя к посту.
    Возвращает True, если жизнь продлена, иначе False."""
    if post.is_golden:
        return False
    # Если у пользователя уже есть комментарий к этому посту — не продлеваем
    if post.comments.filter(author=user, is_active=True).exists():
        return False
    Post.objects.filter(pk=post.pk, is_active=True, is_golden=False).update(
        expires_at=F("expires_at") + timedelta(hours=12)
    )
    return True


def post_list(request):
    now = timezone.now()
    
    # ── Inline search ──
    q = request.GET.get("q", "").strip()
    search_results = None
    if q:
        node_results = Node.objects.filter(
            Q(name__icontains=q) | Q(slug__icontains=q) | Q(description__icontains=q),
            is_active=True,
        )[:10]
        post_results = (
            Post.objects.filter(
                Q(title__icontains=q) | Q(content__icontains=q),
                is_active=True,
                expires_at__gt=now,
            )
            .select_related("author", "node")
            .annotate(like_count=Count("likes", filter=ACTIVE_LIKE))[:20]
        )
        search_results = {"q": q, "nodes": node_results, "posts": post_results}
    
    # ── Regular post list ──
    if not q:
        posts = (
            Post.objects.filter(expires_at__gt=now, is_active=True)
            .select_related("author", "node")
            .annotate(like_count=Count("likes", filter=ACTIVE_LIKE))
            .order_by("-is_golden", "-is_pinned", "-like_count", "-created_at")
        )
    else:
        posts = Post.objects.none()
    
    liked_slugs = set()
    post_ct = ContentType.objects.get_for_model(Post)
    if request.user.is_authenticated:
        check_dying_posts_for_user(request.user)
        liked_ids = Like.objects.filter(
            user=request.user,
            content_type=post_ct,
            object_id__in=posts.values_list("pk", flat=True),
            is_active=True,
        ).values_list("object_id", flat=True)
        liked_slugs = set(
            Post.objects.filter(pk__in=liked_ids).values_list("slug", flat=True)
        )

    context = {
        "posts": posts,
        "liked_slugs": liked_slugs,
        "is_god": is_god(request.user),
        "search_results": search_results,
    }
    if request.user.is_authenticated:
        context.update(get_user_quests_context(request.user))

    return render(request, "forum/post_list.html", context)


def graveyard_list(request):
    posts = Post.objects.filter(is_active=False).select_related("author").only(
        "slug", "title", "author", "expires_at", "pk"
    )
    return render(
        request,
        "forum/graveyard.html",
        {"posts": posts, "is_god": is_god(request.user)},
    )


def post_detail(request, slug):
    return _post_detail_view(request, slug)


def post_detail_in_node(request, node_slug, post_slug):
    """Просмотр поста внутри узла."""
    node = get_object_or_404(Node, slug=node_slug, is_active=True)
    post = get_object_or_404(Post, slug=post_slug, node=node)
    return _post_detail_view(request, post_slug, node=node)


def _post_detail_view(request, slug, node=None):
    post = get_object_or_404(
        Post.objects.select_related("author", "node").annotate(
            like_count=Count("likes", filter=ACTIVE_LIKE)
        ),
        slug=slug,
    )
    if not post.is_active:
        # 410 Gone — семантически корректно для SEO: контент удалён навсегда
        return HttpResponseGone("Пост удалён и больше недоступен.")

    now = timezone.now()
    comment_ct = ContentType.objects.get_for_model(Comment)

    # ── Build infinite comment tree ──
    all_comments = list(
        Comment.objects.filter(
            post=post, is_active=True, expires_at__gt=now
        )
        .select_related("author")
        .annotate(like_count=Count("likes", filter=ACTIVE_LIKE))
        .order_by("created_at")
    )
    comment_dict = {c.pk: c for c in all_comments}
    comment_tree = []
    for c in all_comments:
        c.children = []
        if c.parent_id is None:
            comment_tree.append(c)
        elif c.parent_id in comment_dict:
            comment_dict[c.parent_id].children.append(c)

    liked_post = False
    liked_comment_ids = set()
    if request.user.is_authenticated:
        post_ct = ContentType.objects.get_for_model(Post)
        liked_post = Like.objects.filter(
            user=request.user,
            content_type=post_ct,
            object_id=post.pk,
            is_active=True,
        ).exists()
        all_comment_ids = [c.pk for c in all_comments]
        liked_comment_ids = set(
            Like.objects.filter(
                user=request.user,
                content_type=comment_ct,
                object_id__in=all_comment_ids,
                is_active=True,
            ).values_list("object_id", flat=True)
        )

    # ── Comment form (no cooldown — unlimited comments allowed) ──
    comment_form = None
    if request.user.is_authenticated and post.expires_at > now:
        if request.method == "POST":
            if request.POST.get("reply_to"):
                parent = get_object_or_404(
                    Comment,
                    pk=request.POST.get("reply_to"),
                    post=post,
                )
                text = request.POST.get("text", "").strip()
                if text:
                    Comment.objects.create(
                        post=post,
                        author=request.user,
                        parent=parent,
                        text=text,
                    )
                    return redirect("forum:post_detail", slug=post.slug)
            else:
                comment_form = CommentForm(request.POST)
                if comment_form.is_valid():
                    with transaction.atomic():
                        c = comment_form.save(commit=False)
                        c.post = post
                        c.author = request.user
                        c.save()
                        notify_mentions(c.text, request.user, post.get_absolute_url())
                        remaining_h = max(
                            0,
                            (post.expires_at - timezone.now()).total_seconds()
                            / 3600,
                        )
                        did_extend = extend_post_on_comment(post, request.user)
                        if did_extend and remaining_h:
                            on_post_life_extended(
                                request.user, post.pk, remaining_h
                            )
                    check_post_comment_quests(post)
                    return redirect("forum:post_detail", slug=post.slug)
        else:
            comment_form = CommentForm()

    return render(
        request,
        "forum/post_detail.html",
        {
            "post": post,
            "post_node": node or post.node,
            "comment_tree": comment_tree,
            "comment_form": comment_form,
            "now": now,
            "liked_post": liked_post,
            "liked_comment_ids": liked_comment_ids,
            "can_delete": request.user.is_authenticated
            and (request.user.pk == post.author_id or is_god(request.user)),
            "is_god": is_god(request.user),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def post_create(request, node_slug=None):
    """Создание поста. Если передан node_slug, пост привязывается к узлу.
    Поддерживает загрузку изображений, аудио и GIF в Cloudinary."""
    node = None
    if node_slug:
        node = get_object_or_404(Node, slug=node_slug, is_active=True)
    else:
        # По умолчанию — узел "global"
        node = Node.objects.filter(slug="global", is_active=True).first()

    if request.method == "POST":
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            User = get_user_model()
            post = None
            with transaction.atomic():
                locked = User.objects.select_for_update().get(pk=request.user.pk)
                use_free = locked.has_free_post
                cost = 0 if use_free else POST_CREATION_COST

                if locked.tokens < cost:
                    messages.error(
                        request,
                        f"Недостаточно токенов: создание поста стоит {POST_CREATION_COST}.",
                    )
                else:
                    updates = {
                        "vitality_expires_at": F("vitality_expires_at")
                        + timedelta(days=7),
                    }
                    if use_free:
                        updates["has_free_post"] = False
                    elif cost:
                        updates["tokens"] = F("tokens") - cost

                    User.objects.filter(pk=locked.pk).update(**updates)
                    post = form.save(commit=False)
                    post.author_id = locked.pk
                    if node:
                        post.node = node
                    post.save()

                    if use_free:
                        messages.success(
                            request,
                            "Использован бесплатный пост (награда 7-го дня стрика).",
                        )

            if not post:
                return redirect(request.META.get("HTTP_REFERER") or "forum:post_list")

            # ── Upload media to Cloudinary AFTER transaction ──
            media_type = form.cleaned_data.get("media_type")
            media_source = form.cleaned_data.get("media_source")
            media_file = request.FILES.get("media_file")
            media_url = form.cleaned_data.get("media_url", "")

            final_url = ""
            if media_type and media_file:
                resource_type = "video" if media_type == "audio" else "image"
                final_url = upload_to_cloudinary(media_file, resource_type)
                if not final_url:
                    messages.warning(request, "Не удалось загрузить медиа в Cloudinary. Проверьте API-ключи.")
            elif media_type and media_source == "url" and media_url:
                final_url = media_url

            # ── Notify mentioned users ──
            notify_mentions(post.content, request.user, post.get_absolute_url())

            if final_url and media_type == "image":
                post.image = final_url
                post.save(update_fields=["image"])
            elif final_url and media_type == "audio":
                post.audio = final_url
                post.save(update_fields=["audio"])
            elif final_url and media_type == "gif":
                post.gif = final_url
                post.save(update_fields=["gif"])

            return redirect(post.get_absolute_url())
    else:
        form = PostForm()

    return render(
        request,
        "forum/post_form.html",
        {
            "form": form,
            "node": node,
            "has_free_post": request.user.has_free_post,
            "post_cost": POST_CREATION_COST,
        },
    )


@login_required
@require_http_methods(["POST"])
def post_delete(request, slug):
    # Автор удаляет свой пост; god может удалить любой пост
    if is_god(request.user):
        post = get_object_or_404(Post, slug=slug)
    else:
        post = get_object_or_404(Post, slug=slug, author=request.user)
    if post.is_active:
        post.is_active = False
        post.save(update_fields=["is_active"])
        messages.success(request, f"Пост «{post.title}» отправлен в Кладбище.")
    return redirect("forum:graveyard_list")


@login_required
@require_http_methods(["POST"])
def post_resurrect(request, slug):
    if not is_god(request.user):
        return HttpResponseForbidden("Доступ запрещён.")
    post = get_object_or_404(Post, slug=slug)
    post.is_active = True
    post.expires_at = timezone.now() + timedelta(days=7)
    post.save(update_fields=["is_active", "expires_at"])
    messages.success(request, f"Пост «{post.title}» воскрешён на 7 дней.")
    return redirect("forum:graveyard_list")


@login_required
@require_http_methods(["POST"])
def post_destroy(request, slug):
    if not is_god(request.user):
        return HttpResponseForbidden("Доступ запрещён.")
    post = get_object_or_404(Post, slug=slug)
    title = post.title
    post.delete()
    messages.success(request, f"Пост «{title}» уничтожен безвозвратно.")
    return redirect("forum:graveyard_list")


@login_required
@require_http_methods(["POST"])
def toggle_like_post(request, slug):
    if not allow_like(request.user.pk):
        if wants_json(request):
            return json_like_error(
                request, "Слишком быстро: не более одного лайка в секунду."
            )
        deny_like_message(request)
        return redirect(request.META.get("HTTP_REFERER", "/"))

    post = get_object_or_404(Post, slug=slug)
    if not post.is_active:
        if wants_json(request):
            return JsonResponse(
                {"ok": False, "error": "Пост недоступен."}, status=400
            )
        return redirect(request.META.get("HTTP_REFERER", "/"))

    User = get_user_model()
    ct = ContentType.objects.get_for_model(Post)
    like, _ = Like.objects.get_or_create(
        user=request.user,
        content_type=ct,
        object_id=post.pk,
    )

    reward_message = None
    if like.is_active:
        like.is_active = False
        like.save(update_fields=["is_active"])
        liked = False
    else:
        like.is_active = True
        update_fields = ["is_active"]
        liked = True
        if post.is_golden:
            on_golden_post_liked(request.user, post.pk)
            if not like.granted_golden_reward:
                User.objects.filter(pk=request.user.pk).update(
                    tokens=F("tokens") + GOLDEN_LIKE_REWARD
                )
                like.granted_golden_reward = True
                update_fields.append("granted_golden_reward")
                reward_message = (
                    f"+{GOLDEN_LIKE_REWARD} токенов за лайк Золотого поста!"
                )
        elif not like.granted_time_extension:
            remaining_h = max(
                0, (post.expires_at - timezone.now()).total_seconds() / 3600
            )
            Post.objects.filter(pk=post.pk, is_golden=False).update(
                expires_at=F("expires_at") + timedelta(hours=4)
            )
            on_post_life_extended(request.user, post.pk, remaining_h)
            like.granted_time_extension = True
            update_fields.append("granted_time_extension")
        like.save(update_fields=update_fields)
        check_post_like_quests(post)

    if wants_json(request):
        payload = {
            "ok": True,
            "liked": liked,
            "like_count": post_like_count(post),
        }
        if reward_message:
            payload["message"] = reward_message
        return JsonResponse(payload)

    if reward_message:
        messages.success(request, reward_message)
    referer = request.META.get("HTTP_REFERER")
    return redirect(referer or post.get_absolute_url())


@login_required
@require_http_methods(["POST"])
def toggle_like_comment(request, pk):
    if not allow_like(request.user.pk):
        if wants_json(request):
            return json_like_error(
                request, "Слишком быстро: не более одного лайка в секунду."
            )
        deny_like_message(request)
        return redirect(request.META.get("HTTP_REFERER", "/"))

    comment = get_object_or_404(Comment, pk=pk)
    if not comment.is_active or not comment.post.is_active:
        if wants_json(request):
            return JsonResponse(
                {"ok": False, "error": "Комментарий недоступен."}, status=400
            )
        return redirect(request.META.get("HTTP_REFERER", "/"))

    ct = ContentType.objects.get_for_model(Comment)
    like, _ = Like.objects.get_or_create(
        user=request.user,
        content_type=ct,
        object_id=comment.pk,
    )

    if like.is_active:
        like.is_active = False
        like.save(update_fields=["is_active"])
        liked = False
    else:
        like.is_active = True
        like.save(update_fields=["is_active"])
        liked = True
        check_comment_like_quests(comment)

    if wants_json(request):
        return JsonResponse(
            {
                "ok": True,
                "liked": liked,
                "like_count": comment_like_count(comment),
            }
        )

    referer = request.META.get("HTTP_REFERER")
    return redirect(referer or comment.post.get_absolute_url())


@login_required
@require_http_methods(["POST"])
def toggle_pin_post(request, slug):
    if not is_god(request.user):
        return HttpResponseForbidden("Доступ запрещён.")

    post = get_object_or_404(Post, slug=slug, is_active=True)
    with transaction.atomic():
        if post.is_pinned:
            post.is_pinned = False
            post.save(update_fields=["is_pinned"])
            messages.info(request, f"Пост «{post.title}» откреплён.")
        else:
            Post.objects.filter(is_pinned=True).exclude(pk=post.pk).update(
                is_pinned=False
            )
            post.is_pinned = True
            post.save(update_fields=["is_pinned"])
            messages.success(request, f"Пост «{post.title}» закреплён в ленте.")

    return redirect("forum:post_list")


@login_required
@require_http_methods(["POST"])
def approve_comment(request, pk):
    if not is_god(request.user):
        return HttpResponseForbidden("Доступ запрещён.")
    comment = get_object_or_404(Comment, pk=pk, post__is_golden=True)
    if comment.is_approved:
        messages.info(request, "Комментарий уже одобрен.")
        return redirect(comment.post.get_absolute_url())

    User = get_user_model()
    with transaction.atomic():
        comment.is_approved = True
        update_fields = ["is_approved"]
        if not comment.approval_reward_paid:
            User.objects.filter(pk=comment.author_id).update(
                tokens=F("tokens") + APPROVAL_REWARD
            )
            comment.approval_reward_paid = True
            update_fields.append("approval_reward_paid")
        comment.save(update_fields=update_fields)

    on_golden_comment_approved(comment.author)
    messages.success(
        request,
        f"Комментарий одобрен. Автору начислено {APPROVAL_REWARD} токенов.",
    )
    return redirect(comment.post.get_absolute_url())


@login_required
@require_http_methods(["POST"])
def edit_comment(request, pk):
    """Редактирование комментария: автор может изменить текст, появляется пометка «Изменено»."""
    comment = get_object_or_404(Comment, pk=pk)
    if request.user.pk != comment.author_id:
        return HttpResponseForbidden("Доступ запрещён.")
    if not comment.is_active or not comment.post.is_active:
        messages.error(request, "Комментарий недоступен для редактирования.")
        return redirect(comment.post.get_absolute_url())
    text = request.POST.get("text", "").strip()
    if text:
        comment.text = text
        comment.edited_at = timezone.now()
        comment.save(update_fields=["text", "edited_at"])
        messages.success(request, "Комментарий изменён.")
    return redirect(comment.post.get_absolute_url())


@login_required
@require_http_methods(["POST"])
def delete_comment(request, pk):
    """Удаление комментария: автор или wen3x может удалить любой комментарий/ответ."""
    comment = get_object_or_404(Comment, pk=pk)
    if not (request.user.pk == comment.author_id or is_god(request.user)):
        return HttpResponseForbidden("Доступ запрещён.")
    if not comment.is_active:
        messages.info(request, "Комментарий уже удалён.")
    else:
        comment.is_active = False
        comment.save(update_fields=["is_active"])
        messages.success(request, "Комментарий удалён.")
    return redirect(comment.post.get_absolute_url())


# ── NODES (Узлы) ─────────────────────────────────────────────────────────────

def node_list(request):
    """Список всех активных узлов."""
    nodes = Node.objects.filter(is_active=True).annotate(
        post_count=Count("posts", filter=Q(posts__is_active=True, posts__expires_at__gt=timezone.now())),
        like_count=Count("posts__likes", filter=Q(posts__likes__is_active=True, posts__is_active=True, posts__expires_at__gt=timezone.now())),
    )
    return render(request, "forum/node_list.html", {"nodes": nodes, "is_god": is_god(request.user)})


def node_detail(request, node_slug):
    """Страница узла со списком постов в нём."""
    node = get_object_or_404(Node, slug=node_slug, is_active=True)
    now = timezone.now()
    posts = (
        Post.objects.filter(node=node, expires_at__gt=now, is_active=True)
        .select_related("author")
        .annotate(like_count=Count("likes", filter=ACTIVE_LIKE))
        .order_by("-is_golden", "-is_pinned", "-like_count", "-created_at")
    )
    total_posts = posts.count()
    total_likes = Like.objects.filter(
        content_type=ContentType.objects.get_for_model(Post),
        object_id__in=posts.values_list("pk", flat=True),
        is_active=True,
    ).count()

    liked_slugs = set()
    post_ct = ContentType.objects.get_for_model(Post)
    if request.user.is_authenticated:
        liked_ids = Like.objects.filter(
            user=request.user,
            content_type=post_ct,
            object_id__in=posts.values_list("pk", flat=True),
            is_active=True,
        ).values_list("object_id", flat=True)
        liked_slugs = set(
            Post.objects.filter(pk__in=liked_ids).values_list("slug", flat=True)
        )

    # Подписка на узел
    is_subscribed = False
    node_ban_info = None
    if request.user.is_authenticated:
        is_subscribed = NodeSubscription.objects.filter(
            user=request.user, node=node
        ).exists()
        # Проверяем бан через Python (ловит и битые FK)
        now = timezone.now()
        for ban in Ban.objects.filter(
            user=request.user, expires_at__gt=now
        ).select_related('node')[:10]:
            if ban.node is None:
                node_ban_info = {
                    'type': 'global',
                    'expires_at': ban.expires_at,
                    'reason': ban.reason,
                }
                break
            elif ban.node == node:
                node_ban_info = {
                    'type': 'node',
                    'expires_at': ban.expires_at,
                    'reason': ban.reason,
                }
                break

    # ── Quick media post ──
    if request.method == "POST" and request.POST.get("action") == "quick_media_post":
        if request.user.is_authenticated:
            User = get_user_model()
            title = request.POST.get("title", "").strip() or "📷 Медиа"
            content = request.POST.get("content", "").strip()
            media_file = request.FILES.get("media_file")
            media_url = request.POST.get("media_url", "").strip()
            media_type = request.POST.get("media_type", "")

            if media_file or media_url:
                with transaction.atomic():
                    locked = User.objects.select_for_update().get(pk=request.user.pk)
                    cost = POST_CREATION_COST if not locked.has_free_post else 0
                    if locked.tokens < cost:
                        messages.error(request, f"Недостаточно токенов.")
                    else:
                        updates = {"vitality_expires_at": F("vitality_expires_at") + timedelta(days=7)}
                        if locked.has_free_post:
                            updates["has_free_post"] = False
                        elif cost:
                            updates["tokens"] = F("tokens") - cost
                        User.objects.filter(pk=locked.pk).update(**updates)

                        post = Post.objects.create(
                            author=request.user,
                            node=node,
                            title=title,
                            content=content,
                        )

                        final_url = ""
                        if media_file:
                            resource_type = "video" if media_type == "audio" else "image"
                            final_url = upload_to_cloudinary(media_file, resource_type)
                        elif media_url:
                            final_url = media_url

                        if final_url:
                            if media_type == "image":
                                post.image = final_url
                            elif media_type == "gif":
                                post.gif = final_url
                            elif media_type == "audio":
                                post.audio = final_url
                            post.save(update_fields=["image", "audio", "gif"])

                        notify_mentions(title, request.user, post.get_absolute_url())
                        messages.success(request, "Пост опубликован!")
                        return redirect(post.get_absolute_url())
            else:
                messages.error(request, "Добавьте файл или ссылку.")
        return redirect("forum:node_detail", node_slug=node.slug)

    # ── Golden post creation (только wen3x, с привязкой к узлу) ──
    if request.method == "POST" and request.POST.get("action") == "golden_post_in_node":
        if is_god(request.user):
            title = request.POST.get("golden_title", "").strip()
            content = request.POST.get("golden_content", "").strip()
            if title and content:
                Post.objects.create(
                    author=request.user,
                    node=node,
                    title=title,
                    content=content,
                    is_golden=True,
                )
                messages.success(request, f"Золотой пост «{title}» создан в узле «{node.name}».")
                return redirect("forum:node_detail", node_slug=node.slug)
            else:
                messages.error(request, "Укажите заголовок и текст Золотого поста.")
        else:
            messages.error(request, "Только wen3x может создавать Золотые посты.")
        return redirect("forum:node_detail", node_slug=node.slug)

    return render(
        request,
        "forum/node_detail.html",
        {
            "node": node,
            "posts": posts,
            "liked_slugs": liked_slugs,
            "total_posts": total_posts,
            "total_likes": total_likes,
            "is_subscribed": is_subscribed,
            "is_god": is_god(request.user),
            "node_ban_info": node_ban_info,
        },
    )


@login_required
@require_http_methods(["POST"])
def toggle_node_subscription(request, node_slug):
    """Подписаться/отписаться от узла."""
    node = get_object_or_404(Node, slug=node_slug, is_active=True)
    sub = NodeSubscription.objects.filter(
        user=request.user, node=node
    ).first()
    if sub:
        sub.delete()
        messages.success(request, f"Вы отписались от «{node.name}».")
    else:
        NodeSubscription.objects.create(user=request.user, node=node)
        messages.success(request, f"Вы подписались на «{node.name}». Будут приходить уведомления о постах из этого узла.")
    return redirect("forum:node_detail", node_slug=node.slug)


@login_required
@require_http_methods(["GET", "POST"])
def create_node(request):
    """Создание узла (только wen3x)."""
    if not is_god(request.user):
        return HttpResponseForbidden("Доступ запрещён.")

    if request.method == "POST":
        slug = request.POST.get("slug", "").strip().lower()
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        avatar = request.POST.get("avatar", "").strip()
        header = request.POST.get("header", "").strip()
        if slug and name:
            if Node.objects.filter(slug=slug).exists():
                messages.error(request, f"Узел с таким URL уже существует: /n/{slug}/")
            else:
                Node.objects.create(
                    slug=slug,
                    name=name,
                    description=description,
                    avatar=avatar,
                    header=header,
                    created_by=request.user,
                )
                messages.success(request, f"Узел «{name}» создан: /n/{slug}/")
                return redirect("forum:node_detail", node_slug=slug)
        else:
            messages.error(request, "Укажите URL и название узла.")
        return redirect("forum:create_node")

    return render(request, "forum/node_form.html", {"is_god": is_god(request.user)})


@login_required
@require_http_methods(["GET", "POST"])
def edit_node(request, node_slug):
    """Редактирование узла (только wen3x)."""
    if not is_god(request.user):
        return HttpResponseForbidden("Доступ запрещён.")

    node = get_object_or_404(Node, slug=node_slug)

    if request.method == "POST":
        form = NodeForm(request.POST, instance=node)
        if form.is_valid():
            form.save()
            messages.success(request, f"Узел «{node.name}» обновлён.")
            return redirect("forum:node_detail", node_slug=node.slug)
    else:
        form = NodeForm(instance=node)

    return render(
        request,
        "forum/node_form.html",
        {"form": form, "is_god": is_god(request.user), "editing": True, "node": node},
    )


# ── SEARCH ────────────────────────────────────────────────────────────────────

def search_view(request):
    """Поиск по узлам и постам."""
    q = request.GET.get("q", "").strip()
    node_results = []
    post_results = []
    if q:
        now = timezone.now()
        node_results = Node.objects.filter(
            Q(name__icontains=q) | Q(slug__icontains=q) | Q(description__icontains=q),
            is_active=True,
        )[:10]
        post_results = (
            Post.objects.filter(
                Q(title__icontains=q) | Q(content__icontains=q),
                is_active=True,
                expires_at__gt=now,
            )
            .select_related("author", "node")
            .annotate(like_count=Count("likes", filter=ACTIVE_LIKE))[:20]
        )

    return render(
        request,
        "forum/search.html",
        {
            "q": q,
            "node_results": node_results,
            "post_results": post_results,
            "is_god": is_god(request.user),
        },
    )


# ── DIAGNOSTICS ──────────────────────────────────────────────────────────────

def debug_view(request):
    """Показывает статус системы (только для wen3x)."""
    if not is_god(request.user):
        return HttpResponseForbidden()

    try:
        ban_count = Ban.objects.count()
        ban_table_ok = True
    except Exception:
        ban_count = 0
        ban_table_ok = False

    import subprocess
    try:
        git_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent.parent, stderr=subprocess.STDOUT).decode("utf-8").strip()
    except Exception:
        git_hash = "unknown"

    import sys
    mod = sys.modules.get(__name__)
    has_is_banned = hasattr(mod, 'is_banned') if mod else False
    has_ban_banner = True  # Will check if base.html has it
    try:
        with open(Path(__file__).resolve().parent.parent / 'templates' / 'base.html', 'r', encoding='utf-8') as f:
            content = f.read()
            has_ban_banner = 'active_ban' in content and 'entropy-bottom-nav' in content
    except Exception:
        has_ban_banner = False

    now = timezone.now()
    
    # ── Detailed ban info ──
    ban_rows = ""
    if ban_table_ok:
        bans = Ban.objects.select_related('user', 'node').order_by('-created_at')[:20]
        for b in bans:
            uname = b.user.username
            target = "🌐 глобальный" if b.node is None else f"📁 {b.node.name}"
            expires = b.expires_at.strftime("%d.%m %H:%M")
            expired = "(истёк)" if b.expires_at < now else "(АКТИВЕН)"
            reason = f"· {b.reason}" if b.reason else ""
            
            # RAW data dump for each ban
            pk = b.pk
            raw_node_id = Ban.objects.filter(pk=b.pk).values_list('node_id', flat=True).first()
            node_id_str = f"node_id={raw_node_id}"
            
            # Manual test: count all bans for this user
            all_for_user = Ban.objects.filter(user=b.user).count()
            
            # Manual test: count active bans for this user (no node filter)
            active_no_node = Ban.objects.filter(user=b.user, expires_at__gt=now).count()
            
            # Manual test: count active bans for this user with node__isnull=True
            active_isnull = Ban.objects.filter(user=b.user, expires_at__gt=now, node__isnull=True).count()
            
            # Manual test: count with node_id__isnull=True (same thing, raw column)
            active_isnull_raw = Ban.objects.filter(user=b.user, expires_at__gt=now, node_id__isnull=True).count()
            
            # Also test is_banned for each banned user
            test_global = "✅" if is_banned(b.user) else "❌"
            test_with_node = ""
            if b.node:
                test_with_node = f" | is_banned(+node): {'✅' if is_banned(b.user, b.node) else '❌'}"
            ban_rows += f"<tr><td>{uname}</td><td>{target}</td><td>{expires}</td>"
            ban_rows += f"<td style='color:{'#ff4444' if '(АКТИВЕН)' in expired else '#888'}'>{expired}</td>"
            ban_rows += f"<td>{reason}</td>"
            ban_rows += f"<td>{test_global}{test_with_node}</td>"
            ban_rows += f"<td style='font-size:0.75rem;color:#aaa'>"
            ban_rows += f"pk={pk}, {node_id_str}, все={all_for_user}, active={active_no_node}, active+isnull={active_isnull}, active+id_isnull={active_isnull_raw}"
            ban_rows += f"</td></tr>"
    
    # ── Test is_banned for current user ──
    self_ban_status = is_banned(request.user) if request.user.is_authenticated else False
    self_ban_info = f"{'✅ ЗАБАНЕН' if self_ban_status else '❌ НЕ забанен'}" if request.user.is_authenticated else "не авторизован"
    
    # ── Show middleware exists ──
    from django.conf import settings
    has_ban_mw = 'accounts.middleware.BanMiddleware' in settings.MIDDLEWARE
    
    html = f"""
    <html><body style="font-family:monospace;padding:2rem;background:#000;color:#0f0;">
    <h2>🔍 Диагностика Entropy</h2>
    <table border="1" style="border-collapse:collapse;border-color:#333;width:100%;">
    <tr><td>Git commit</td><td>{git_hash}</td></tr>
    <tr><td>Серверное время</td><td>{now.strftime('%d.%m.%Y %H:%M:%S %Z')}</td></tr>
    <tr><td>Ban table exists</td><td>{'✅' if ban_table_ok else '❌'}</td></tr>
    <tr><td>Ban records</td><td>{ban_count}</td></tr>
    <tr><td>BanMiddleware в settings</td><td>{'✅' if has_ban_mw else '❌'}</td></tr>
    <tr><td>is_banned() в коде</td><td>{'✅' if has_is_banned else '❌'}</td></tr>
    <tr><td>base.html (nav+ban+inlineCSS)</td><td>{'✅' if has_ban_banner else '❌'}</td></tr>
    <tr><td>ВЕРДИКТ</td><td>{'НОВЫЙ код 🟢' if has_is_banned else 'СТАРЫЙ код 🔴'}</td></tr>
    <tr><td><b>ВАШ СТАТУС</b></td><td><b>{self_ban_info}</b></td></tr>
    </table>
    <h3>📋 Все баны в БД (с тестом is_banned для каждого):</h3>
    <table border="1" style="border-collapse:collapse;border-color:#333;width:100%;">
    <tr><th>Пользователь</th><th>Тип</th><th>Истекает</th><th>Статус</th><th>Причина</th><th>is_banned()</th><th>RAW (pk, node_id, counts)</th></tr>
    {ban_rows or '<tr><td colspan="6">Нет банов</td></tr>'}
    </table>
    <p>✅ = новая версия | ❌ = старая версия | (АКТИВЕН) = бан ещё действует</p>
    <p><b>ВАШ СТАТУС:</b> is_banned(request.user) = {self_ban_status}</p>
    <p>Подсказка: если <b>(АКТИВЕН)</b> но ❌ — баны есть, но is_banned() их не находит (ошибка).</p>
    </body></html>
    """
    return HttpResponse(html, content_type="text/html")


# ── CUSTOM 404 ERROR HANDLER ──────────────────────────────────────────────

def custom_404(request, exception=None):
    """Кастомная страница 404 ошибки вместо стандартной."""
    return render(request, "404.html", status=404)


# ── PWA: Service Worker (/sw.js) ──────────────────────────────────────────

def service_worker(request):
    """Serve the service worker from the site root so its scope covers /."""
    sw_path = Path(__file__).resolve().parent.parent / "static" / "js" / "sw.js"
    return HttpResponse(
        sw_path.read_text("utf-8"),
        content_type="application/javascript",
    )


# ── PWA: manifest.json ──────────────────────────────────────────────────────

def manifest_json(request):
    """Web App Manifest для PWA."""
    base = f"{request.scheme}://{request.get_host()}"
    return JsonResponse(
        {
            "name": "Entropy",
            "short_name": "Entropy",
            "description": "Форум с энтропией — посты живут ограниченное время",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#000000",
            "theme_color": "#000000",
            "orientation": "portrait",
            "icons": [
                {
                    "src": f"{base}/static/img/favicon.png",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": f"{base}/static/img/favicon.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any",
                },
            ],
        },
        content_type="application/manifest+json",
    )


# ── SEO: robots.txt ──────────────────────────────────────────────────────────

def robots_txt(request):
    """Разрешаем индексацию сайта, закрываем служебные разделы."""
    base_url = f"{request.scheme}://{request.get_host()}"
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /secret-panel/",
        "Disallow: /accounts/login/",
        "Disallow: /accounts/register/",
        "Disallow: /accounts/logout/",
        f"Sitemap: {base_url}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


# ── SEO: sitemap.xml ─────────────────────────────────────────────────────────

def sitemap_xml(request):
    """Динамический sitemap: только активные посты с не истёкшим сроком."""
    now = timezone.now()
    posts = (
        Post.objects.filter(is_active=True, expires_at__gt=now)
        .only("slug", "created_at")
        .order_by("-created_at")
    )
    base_url = f"{request.scheme}://{request.get_host()}"
    return render(
        request,
        "forum/sitemap.xml",
        {"posts": posts, "base_url": base_url},
        content_type="application/xml",
    )
