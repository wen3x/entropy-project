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
from .models import ShopItem
from .quests import ensure_default_quests, get_user_quests_context
from .shop import ensure_default_shop_items, get_visible_shop_items, purchase_item, reset_theme
from .streaks import STREAK_MAX_DAYS, STREAK_SCHEDULE, get_streak_page_context
from .theme import get_palette, PALETTES


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


def profile_redirect(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return redirect("profile_detail", username=request.user.username)


def profile_detail(request, username):
    profile_user = get_object_or_404(
        get_user_model(), username__iexact=username
    )
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
    quest_ctx = {}
    if is_own:
        ensure_default_quests()
        quest_ctx = get_user_quests_context(request.user)
        streak_reward = request.session.pop("streak_reward", None)

    profile_color = profile_user.profile_color or ""
    profile_theme_id = profile_color if profile_color in PALETTES else "default"
    profile_theme = get_palette(profile_color)

    return render(
        request,
        "accounts/profile.html",
        {
            "profile_user": profile_user,
            "is_own_profile": is_own,
            "streak_reward": streak_reward,
            "post_count": post_count,
            "active_posts": active_posts,
            "user_posts": user_posts,
            "profile_theme": profile_theme,
            "profile_theme_id": profile_theme_id,
            **quest_ctx,
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


def streaks_page(request):
    if request.user.is_authenticated:
        ctx = get_streak_page_context(request.user)
    else:
        ctx = {
            "schedule": STREAK_SCHEDULE,
            "current_streak": 0,
            "progress_pct": 0,
            "streak_max_days": STREAK_MAX_DAYS,
            "has_free_post": False,
        }
    return render(request, "accounts/streaks.html", ctx)


def vitality_expired(request):
    return render(request, "accounts/vitality_expired.html")


def shop_view(request):
    ensure_default_shop_items()
    items = get_visible_shop_items()

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, "Войдите в аккаунт для покупок.")
            return redirect("shop")
        action = request.POST.get("action", "buy")

        if action == "reset_theme":
            ok, msg = reset_theme(request.user)
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return redirect("shop")

        item_code = request.POST.get("item_code", "")
        color = request.POST.get("color", "").strip().lower()
        item = ShopItem.objects.filter(code=item_code, visible_in_shop=True).first()
        if not item:
            messages.error(request, "Товар не найден или скрыт.")
        else:
            ok, msg = purchase_item(request.user, item, color=color)
            if ok:
                messages.success(request, msg)
                request.user.refresh_from_db()
            else:
                messages.error(request, msg)
        return redirect("shop")

    if request.user.is_authenticated:
        user_tokens = request.user.tokens
        has_basic_colors = request.user.has_basic_colors
        has_gold_color = request.user.has_gold_color
        current_color = request.user.profile_color
    else:
        user_tokens = 0
        has_basic_colors = False
        has_gold_color = False
        current_color = ""

    return render(
        request,
        "accounts/shop.html",
        {
            "shop_items": items,
            "user_tokens": user_tokens,
            "has_basic_colors": has_basic_colors,
            "has_gold_color": has_gold_color,
            "current_color": current_color,
        },
    )


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
        elif action == "toggle_shop_item":
            item_id = request.POST.get("item_id")
            item = ShopItem.objects.filter(pk=item_id).first()
            if item:
                item.visible_in_shop = not item.visible_in_shop
                item.save(update_fields=["visible_in_shop"])
                state = "включён" if item.visible_in_shop else "скрыт"
                messages.success(request, f"«{item.title}» {state} в магазине.")
            else:
                messages.error(request, "Товар не найден.")
        return redirect("secret_panel")

    ensure_default_shop_items()
    return render(
        request,
        "accounts/secret_panel.html",
        {"shop_items": ShopItem.objects.order_by("sort_order", "id")},
    )
