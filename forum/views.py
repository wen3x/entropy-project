from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q
from django.http import Http404, HttpResponseForbidden
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

    return render(
        request,
        "forum/post_list.html",
        {"posts": posts, "liked_slugs": liked_slugs},
    )


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
        raise Http404("Пост в архиве — просмотр недоступен.")

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
                            extend_post_on_comment(post)
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
            and request.user.pk == post.author_id,
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
    post = get_object_or_404(Post, slug=slug, author=request.user)
    if post.is_active:
        post.is_active = False
        post.save(update_fields=["is_active"])
        messages.success(request, "Пост отправлен в Кладбище.")
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
        deny_like_message(request)
        return redirect(request.META.get("HTTP_REFERER", "/"))

    post = get_object_or_404(Post, slug=slug)
    if not post.is_active:
        return redirect(request.META.get("HTTP_REFERER", "/"))

    User = get_user_model()
    ct = ContentType.objects.get_for_model(Post)
    like, _ = Like.objects.get_or_create(
        user=request.user,
        content_type=ct,
        object_id=post.pk,
    )

    if like.is_active:
        like.is_active = False
        like.save(update_fields=["is_active"])
    else:
        like.is_active = True
        update_fields = ["is_active"]
        if post.is_golden:
            if not like.granted_golden_reward:
                User.objects.filter(pk=request.user.pk).update(
                    tokens=F("tokens") + GOLDEN_LIKE_REWARD
                )
                like.granted_golden_reward = True
                update_fields.append("granted_golden_reward")
                messages.success(request, f"+{GOLDEN_LIKE_REWARD} токенов за лайк Золотого поста!")
        elif not like.granted_time_extension:
            Post.objects.filter(pk=post.pk, is_golden=False).update(
                expires_at=F("expires_at") + timedelta(hours=4)
            )
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

    referer = request.META.get("HTTP_REFERER")
    return redirect(referer or post.get_absolute_url())


@login_required
@require_http_methods(["POST"])
def toggle_like_comment(request, pk):
    if not allow_like(request.user.pk):
        deny_like_message(request)
        return redirect(request.META.get("HTTP_REFERER", "/"))

    comment = get_object_or_404(Comment, pk=pk)
    if not comment.is_active or not comment.post.is_active:
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
    else:
        like.is_active = True
        like.save(update_fields=["is_active"])
        check_comment_like_quests(comment)

    referer = request.META.get("HTTP_REFERER")
    return redirect(referer or comment.post.get_absolute_url())


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

    messages.success(
        request,
        f"Комментарий одобрен. Автору начислено {APPROVAL_REWARD} токенов.",
    )
    return redirect(comment.post.get_absolute_url())
