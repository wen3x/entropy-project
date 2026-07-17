from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q
from django.http import Http404, HttpResponse, HttpResponseForbidden, HttpResponseGone, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.notifications import (
    check_dying_posts_for_user,
    notify_post_liked,
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

from .forms import CommentForm, PostForm
from .models import Comment, Like, Post
from .rate_limit import allow_like, deny_like_message

POST_CREATION_COST = 25
ACTIVE_LIKE = Q(likes__is_active=True)
GOLDEN_LIKE_REWARD = 10
APPROVAL_REWARD = 100


def is_god(user) -> bool:
    return user.is_authenticated and user.username == "wen3x"


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


def extend_post_on_comment(post: Post):
    if post.is_golden:
        return
    Post.objects.filter(pk=post.pk, is_active=True, is_golden=False).update(
        expires_at=F("expires_at") + timedelta(hours=12)
    )


def post_list(request):
    now = timezone.now()
    posts = (
        Post.objects.filter(expires_at__gt=now, is_active=True)
        .select_related("author")
        .annotate(like_count=Count("likes", filter=ACTIVE_LIKE))
        .order_by("-is_golden", "-is_pinned", "-like_count", "-created_at")
    )
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
    post = get_object_or_404(
        Post.objects.select_related("author").annotate(
            like_count=Count("likes", filter=ACTIVE_LIKE)
        ),
        slug=slug,
    )
    if not post.is_active:
        # 410 Gone — семантически корректно для SEO: контент удалён навсегда
        return HttpResponseGone("Пост удалён и больше недоступен.")

    now = timezone.now()
    top_comments = (
        post.comments.filter(
            expires_at__gt=now,
            is_active=True,
            parent__isnull=True,
        )
        .select_related("author")
        .prefetch_related(
            Prefetch(
                "replies",
                queryset=Comment.objects.filter(is_active=True, expires_at__gt=now)
                .select_related("author")
                .annotate(like_count=Count("likes", filter=ACTIVE_LIKE))
                .order_by("created_at"),
            )
        )
        .annotate(like_count=Count("likes", filter=ACTIVE_LIKE))
    )
    comment_ct = ContentType.objects.get_for_model(Comment)

    liked_post = False
    liked_comment_ids = set()
    has_top_level_comment = False
    if request.user.is_authenticated:
        post_ct = ContentType.objects.get_for_model(Post)
        liked_post = Like.objects.filter(
            user=request.user,
            content_type=post_ct,
            object_id=post.pk,
            is_active=True,
        ).exists()
        all_comment_ids = list(top_comments.values_list("pk", flat=True))
        for tc in top_comments:
            all_comment_ids.extend(tc.replies.values_list("pk", flat=True))
        liked_comment_ids = set(
            Like.objects.filter(
                user=request.user,
                content_type=comment_ct,
                object_id__in=all_comment_ids,
                is_active=True,
            ).values_list("object_id", flat=True)
        )
        has_top_level_comment = post.comments.filter(
            author=request.user, parent__isnull=True
        ).exists()

    comment_form = None
    if request.user.is_authenticated and post.expires_at > now:
        if request.method == "POST":
            if request.POST.get("reply_to"):
                parent = get_object_or_404(
                    Comment,
                    pk=request.POST.get("reply_to"),
                    post=post,
                    parent__isnull=True,
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
                if has_top_level_comment:
                    messages.error(
                        request,
                        "Под постом можно оставить только одно мнение (один комментарий верхнего уровня).",
                    )
                else:
                    comment_form = CommentForm(request.POST)
                    if comment_form.is_valid():
                        with transaction.atomic():
                            c = comment_form.save(commit=False)
                            c.post = post
                            c.author = request.user
                            c.save()
                            remaining_h = max(
                                0,
                                (post.expires_at - timezone.now()).total_seconds()
                                / 3600,
                            )
                            extend_post_on_comment(post)
                            on_post_life_extended(
                                request.user, post.pk, remaining_h
                            )
                        check_post_comment_quests(post)
                        return redirect("forum:post_detail", slug=post.slug)
        else:
            if not has_top_level_comment:
                comment_form = CommentForm()

    return render(
        request,
        "forum/post_detail.html",
        {
            "post": post,
            "top_comments": top_comments,
            "comment_form": comment_form,
            "now": now,
            "liked_post": liked_post,
            "liked_comment_ids": liked_comment_ids,
            "can_delete": request.user.is_authenticated
            and (request.user.pk == post.author_id or is_god(request.user)),
            "is_god": is_god(request.user),
            "has_top_level_comment": has_top_level_comment,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def post_create(request):
    if request.method == "POST":
        form = PostForm(request.POST)
        if form.is_valid():
            User = get_user_model()
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
                    post.save()
                    if use_free:
                        messages.success(
                            request,
                            "Использован бесплатный пост (награда 7-го дня стрика).",
                        )
                    return redirect(post.get_absolute_url())
    else:
        form = PostForm()

    return render(
        request,
        "forum/post_form.html",
        {
            "form": form,
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
        notify_post_liked(
            post.author,
            request.user.username,
            post.title,
            post.get_absolute_url(),
        )

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
