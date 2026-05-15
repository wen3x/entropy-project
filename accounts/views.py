from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import F
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from forum.models import Post

from .forms import RegistrationForm
from .quests import ensure_default_quests, get_user_quests_context
from .streaks import get_streak_page_context


def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            return render(
                request,
                "accounts/register_done.html",
                {"username": form.cleaned_data["username"]},
            )
    else:
        form = RegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile_redirect(request):
    return redirect("profile_detail", user_id=request.user.pk)


@login_required
def profile_detail(request, user_id):
    profile_user = get_object_or_404(get_user_model(), pk=user_id)
    is_own = request.user.pk == profile_user.pk

    now = timezone.now()
    if is_own:
        post_count = Post.objects.filter(author=profile_user).count()
        active_posts = Post.objects.filter(
            author=profile_user, is_active=True, expires_at__gt=now
        ).count()
        user_posts = None
    else:
        post_count = Post.objects.filter(
            author=profile_user, is_active=True, expires_at__gt=now
        ).count()
        active_posts = post_count
        user_posts = (
            Post.objects.filter(
                author=profile_user, is_active=True, expires_at__gt=now
            )
            .order_by("-created_at")[:10]
        )

    quest_items = []
    streak_reward = None
    if is_own:
        ensure_default_quests()
        quest_items = get_user_quests_context(request.user)
        streak_reward = request.session.pop("streak_reward", None)

    return render(
        request,
        "accounts/profile.html",
        {
            "profile_user": profile_user,
            "is_own_profile": is_own,
            "quest_items": quest_items,
            "streak_reward": streak_reward,
            "post_count": post_count,
            "active_posts": active_posts,
            "user_posts": user_posts,
        },
    )


@login_required
def notifications_list(request):
    from accounts.models import Notification

    notes = Notification.objects.filter(user=request.user)[:50]
    return render(request, "accounts/notifications.html", {"notifications": notes})


@login_required
@require_http_methods(["POST"])
def notifications_mark_read(request):
    from accounts.models import Notification

    Notification.objects.filter(user=request.user, is_read=False).update(
        is_read=True
    )
    return redirect("notifications_list")


@login_required
def streaks_page(request):
    return render(
        request,
        "accounts/streaks.html",
        get_streak_page_context(request.user),
    )


def vitality_expired(request):
    return render(request, "accounts/vitality_expired.html")


@login_required
def secret_panel(request):
    if request.user.username != "wen3x":
        return HttpResponseForbidden("Доступ запрещён.")

    if request.method == "POST":
        action = request.POST.get("action")
        from accounts.models import User

        if action == "add_tokens":
            User.objects.filter(pk=request.user.pk).update(tokens=F("tokens") + 100)
            request.user.refresh_from_db()
            messages.success(request, "+100 токенов начислено.")
        elif action == "extend_vitality":
            User.objects.filter(pk=request.user.pk).update(
                vitality_expires_at=F("vitality_expires_at") + timedelta(days=30)
            )
            request.user.refresh_from_db()
            messages.success(request, "Срок жизни аккаунта продлён на 30 дней.")
        elif action == "golden_post":
            title = request.POST.get("golden_title", "").strip()
            content = request.POST.get("golden_content", "").strip()
            if title and content:
                from forum.models import Post

                post = Post.objects.create(
                    author=request.user,
                    title=title,
                    content=content,
                    is_golden=True,
                )
                messages.success(
                    request,
                    f"Золотой пост «{post.title}» создан (24 ч, код: {post.slug}).",
                )
            else:
                messages.error(request, "Укажите заголовок и текст Золотого поста.")
        return redirect("secret_panel")

    return render(request, "accounts/secret_panel.html")
