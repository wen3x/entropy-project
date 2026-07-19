import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.core.management import call_command
from django.db.models import F
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from forum.models import Post

from .forms import RegistrationForm
from forum.models import Node

from .models import Ban, ShopItem
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


def profile_old_redirect(request, username):
    """Редирект со старого /profile/username/ на /u/@username/"""
    return redirect("profile_detail", username=username, permanent=True)


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

    # Проверка роли пользователя
    god_username = getattr(settings, 'GOD_USERNAME', 'admin')
    is_profile_god = profile_user.username == god_username
    is_profile_moderator = False
    if not is_profile_god:
        from .models import Moderator
        is_profile_moderator = Moderator.objects.filter(user=profile_user).exists()

    return render(
        request,
        "accounts/profile.html",
        {
            "profile_user": profile_user,
            "is_own_profile": is_own,
            "is_profile_god": is_profile_god,
            "is_profile_moderator": is_profile_moderator,
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


@login_required
@require_http_methods(["POST"])
def save_push_subscription(request):
    """Сохранить push-подписку браузера."""
    from accounts.models import PushSubscription

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    endpoint = data.get("endpoint", "")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh", "")
    auth = keys.get("auth", "")

    if not endpoint or not p256dh or not auth:
        return JsonResponse({"ok": False, "error": "Missing fields"}, status=400)

    PushSubscription.objects.update_or_create(
        user=request.user,
        endpoint=endpoint,
        defaults={"p256dh": p256dh, "auth": auth},
    )
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["POST"])
def delete_push_subscription(request):
    """Удалить push-подписку браузера."""
    from accounts.models import PushSubscription

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    endpoint = data.get("endpoint", "")
    if endpoint:
        PushSubscription.objects.filter(
            user=request.user, endpoint=endpoint
        ).delete()
    return JsonResponse({"ok": True})


@require_http_methods(["GET"])
def online_count(request):
    """Сколько авторизованных людей сейчас на форуме (активны в последние 5 минут)."""
    from django.contrib.sessions.models import Session

    now = timezone.now()
    cutoff = now - timedelta(minutes=5)
    cutoff_ts = cutoff.timestamp()

    sessions = Session.objects.filter(expire_date__gte=now)
    count = 0
    for s in sessions.iterator():
        try:
            data = s.get_decoded()
            # Считаем только авторизованных (есть _auth_user_id в сессии)
            if data.get("_auth_user_id") and data.get("last_ping", 0) >= cutoff_ts:
                count += 1
        except (ValueError, TypeError, KeyError):
            continue

    return JsonResponse({"count": count})


@require_http_methods(["GET"])
def vapid_public_key(request):
    """Отдать публичный VAPID ключ для подписки на push."""
    return JsonResponse({"public_key": settings.WEBPUSH_VAPID_PUBLIC_KEY})



@require_http_methods(["GET"])
def cron_trigger(request):
    """Запустить send_random_post_notifications по токену (бесплатная замена Render Cron)."""
    token = request.GET.get("token", "")
    expected = settings.CRON_SECRET_TOKEN

    if not expected:
        return JsonResponse({"ok": False, "error": "CRON_SECRET_TOKEN not configured"}, status=500)
    if token != expected:
        return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)

    try:
        call_command("send_random_post_notifications")
        return JsonResponse({"ok": True, "message": "Notifications sent"})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


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
        owned_colors = request.user.owned_colors_list
        current_color = request.user.profile_color
    else:
        user_tokens = 0
        owned_colors = []
        current_color = ""

    return render(
        request,
        "accounts/shop.html",
        {
            "shop_items": items,
            "user_tokens": user_tokens,
            "owned_colors": owned_colors,
            "current_color": current_color,
        },
    )


@login_required
def inventory_view(request):
    """Страница инвентаря — просмотр и применение купленных тем."""
    from .theme import PALETTES

    User = get_user_model()
    user = request.user
    owned_colors = user.owned_colors_list
    current_color = user.profile_color or "default"

    # Все доступные цвета с их палитрами
    theme_list = []
    for color_key in owned_colors:
        palette = PALETTES.get(color_key)
        if not palette:
            continue
        theme_list.append({
            "key": color_key,
            "name": {
                "ice": "Ледяное сияние",
                "matrix": "Матрица",
                "sunset": "Закат энтропии",
                "gold": "Золотой",
                "red": "Красный",
                "blue": "Синий",
                "green": "Зелёный",
            }.get(color_key, color_key),
            "color": palette["fg"],
            "is_active": color_key == current_color,
        })

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "apply_theme":
            theme_key = request.POST.get("theme_key", "")
            if theme_key in owned_colors:
                User.objects.filter(pk=user.pk).update(profile_color=theme_key)
                messages.success(request, f"Тема применена.")
            else:
                messages.error(request, "У вас нет этой темы.")
            return redirect("inventory")
        elif action == "reset_theme":
            ok, msg = reset_theme(user)
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return redirect("inventory")

    return render(request, "accounts/inventory.html", {
        "theme_list": theme_list,
        "current_color": current_color,
        "owned_count": len(owned_colors),
    })


@login_required
def secret_panel(request):
    god_username = getattr(settings, 'GOD_USERNAME', 'admin')
    if request.user.username != god_username:
        return HttpResponseForbidden("Доступ запрещён.")

    User = get_user_model()

    if request.method == "POST":
        action = request.POST.get("action")

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
        elif action == "ban_user":
            username = request.POST.get("ban_username", "").strip()
            node_slug = request.POST.get("ban_node", "").strip()
            hours = request.POST.get("ban_hours", "").strip()

            if not username or not hours:
                messages.error(request, "Укажите ник и время бана.")
            else:
                try:
                    target_user = User.objects.get(username__iexact=username)
                except User.DoesNotExist:
                    messages.error(request, f"Пользователь «{username}» не найден.")
                    return redirect("secret_panel")

                try:
                    duration = float(hours)
                    if duration <= 0:
                        raise ValueError
                except (ValueError, TypeError):
                    messages.error(request, "Время должно быть положительным числом (часы).")
                    return redirect("secret_panel")

                node = None
                ban_type = "глобальный"
                if node_slug:
                    node = Node.objects.filter(slug=node_slug).first()
                    if not node:
                        messages.error(request, f"Узел «{node_slug}» не найден.")
                        return redirect("secret_panel")
                    ban_type = f"узел «{node.name}»"

                ban = Ban.objects.create(
                    user=target_user,
                    node=node,
                    expires_at=timezone.now() + timedelta(hours=duration),
                    reason=request.POST.get("ban_reason", "").strip(),
                )
                # Уведомление забаненному
                expire_str = ban.expires_at.strftime('%d.%m %H:%M')
                if node:
                    note_msg = (
                        f"Вы забанены в узле «{node.name}» до {expire_str}."
                    )
                else:
                    note_msg = (
                        f"Вы забанены глобально до {expire_str}."
                    )
                if ban.reason:
                    note_msg += f" Причина: {ban.reason}"
                from accounts.notifications import notify
                notify(target_user, 'ban', note_msg)

                messages.success(
                    request,
                    f"Пользователь «{target_user.username}» забанен ({ban_type}) на {duration} ч.",
                )
        elif action == "unban_user":
            ban_id = request.POST.get("ban_id", "")
            ban = Ban.objects.filter(pk=ban_id).first()
            if ban:
                target = ban.user.username
                ban.delete()
                messages.success(request, f"Бан пользователя «{target}» снят.")
            else:
                messages.error(request, "Бан не найден.")
        elif action == "toggle_anonymous":
            user = request.user
            user.is_anonymous_mode = not user.is_anonymous_mode
            user.save(update_fields=["is_anonymous_mode"])
            state = "включён" if user.is_anonymous_mode else "выключен"
            messages.success(request, f"Анонимный режим {state}.")
        elif action == "add_moderator":
            username = request.POST.get("mod_username", "").strip()
            node_slug = request.POST.get("mod_node", "").strip()

            if not username:
                messages.error(request, "Укажите ник пользователя.")
            else:
                try:
                    target_user = User.objects.get(username__iexact=username)
                except User.DoesNotExist:
                    messages.error(request, f"Пользователь «{username}» не найден.")
                    return redirect("secret_panel")

                node = None
                scope = "весь форум"
                if node_slug:
                    node = Node.objects.filter(slug=node_slug).first()
                    if not node:
                        messages.error(request, f"Узел «{node_slug}» не найден.")
                        return redirect("secret_panel")
                    scope = f"узел «{node.name}»"

                from .models import Moderator
                _, created = Moderator.objects.get_or_create(
                    user=target_user,
                    node=node,
                    defaults={"created_by": request.user},
                )
                if created:
                    messages.success(
                        request,
                        f"Пользователь «{target_user.username}» назначен модератором ({scope}).",
                    )
                else:
                    messages.info(
                        request,
                        f"Пользователь «{target_user.username}» уже является модератором ({scope}).",
                    )
        elif action == "remove_moderator":
            mod_id = request.POST.get("mod_id", "")
            from .models import Moderator
            mod = Moderator.objects.filter(pk=mod_id).first()
            if mod:
                target = mod.user.username
                mod.delete()
                messages.success(request, f"Модератор «{target}» снят.")
            else:
                messages.error(request, "Модератор не найден.")

        return redirect("secret_panel")

    ensure_default_shop_items()
    now = timezone.now()
    active_bans = Ban.objects.filter(expires_at__gt=now).select_related("user", "node").order_by("-created_at")[:50]
    from .models import Moderator
    moderators = Moderator.objects.select_related("user", "node", "created_by").order_by("-created_at")[:50]
    return render(
        request,
        "accounts/secret_panel.html",
        {
            "shop_items": ShopItem.objects.order_by("sort_order", "id"),
            "active_bans": active_bans,
            "moderators": moderators,
            "nodes": Node.objects.filter(is_active=True).order_by("name"),
            "anonymous_mode": request.user.is_anonymous_mode,
        },
    )


# ── ЖАЛОБЫ ───────────────────────────────────────────────────────────────────


def _can_handle_complaints(user) -> bool:
    """Проверить, может ли пользователь просматривать/обрабатывать жалобы."""
    if not user.is_authenticated:
        return False
    god_username = getattr(settings, 'GOD_USERNAME', 'admin')
    if user.username == god_username:
        return True
    from .models import Moderator
    # Модератор может видеть жалобы, если он глобальный или привязан к любому узлу
    return Moderator.objects.filter(user=user).exists()


@login_required
def complaints_list(request):
    """Страница со списком жалоб (доступна администратору и модераторам)."""
    if not _can_handle_complaints(request.user):
        return HttpResponseForbidden("Доступ запрещён.")

    from .models import Complaint
    from django.contrib.contenttypes.models import ContentType

    status_filter = request.GET.get("status", "")
    complaints_qs = Complaint.objects.select_related("reporter", "resolved_by").order_by("-created_at")
    if status_filter in ("new", "resolved", "dismissed"):
        complaints_qs = complaints_qs.filter(status=status_filter)

    complaints = list(complaints_qs[:100])

    # Batch-load reported objects (избегаем N+1)
    post_ct = ContentType.objects.get_for_model(Post)
    from forum.models import Comment as ForumComment
    post_ids = [c.object_id for c in complaints if c.content_type_id == post_ct.pk]
    comment_ids = [c.object_id for c in complaints if c.content_type_id != post_ct.pk]
    posts_map = {p.pk: p for p in Post.objects.filter(pk__in=post_ids).only("title", "slug", "is_active", "node_id")}
    comments_map = {c.pk: c for c in ForumComment.objects.filter(pk__in=comment_ids).select_related("post").only(
        "text", "post_id", "is_active"
    )}
    for c in complaints:
        c.reported_object = posts_map.get(c.object_id) if c.content_type_id == post_ct.pk else comments_map.get(c.object_id)

    return render(
        request,
        "accounts/complaints.html",
        {
            "complaints": complaints,
            "current_status": status_filter,
        },
    )


@login_required
@require_http_methods(["POST"])
def submit_complaint(request):
    """Отправить жалобу на пост или комментарий."""
    from .models import Complaint
    from django.contrib.contenttypes.models import ContentType

    content_type_name = request.POST.get("content_type", "")
    object_id = request.POST.get("object_id", "")
    reason = request.POST.get("reason", "")
    message = request.POST.get("message", "").strip()

    if not content_type_name or not object_id or not reason:
        messages.error(request, "Заполните обязательные поля.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    try:
        object_id = int(object_id)
    except (ValueError, TypeError):
        messages.error(request, "Некорректный ID объекта.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    # Определяем content type
    ct_map = {
        "post": ContentType.objects.get_for_model(Post),
    }
    from forum.models import Comment
    ct_map["comment"] = ContentType.objects.get_for_model(Comment)

    ct = ct_map.get(content_type_name)
    if not ct:
        messages.error(request, "Некорректный тип контента.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    # Проверяем, что объект существует
    model_class = ct.model_class()
    obj = model_class.objects.filter(pk=object_id).first()
    if not obj:
        messages.error(request, "Объект не найден.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    # Проверяем, не отправлял ли пользователь уже жалобу на этот объект
    existing = Complaint.objects.filter(
        reporter=request.user,
        content_type=ct,
        object_id=object_id,
        status="new",
    ).exists()
    if existing:
        messages.info(request, "Вы уже отправляли жалобу на этот контент.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    complaint = Complaint.objects.create(
        reporter=request.user,
        content_type=ct,
        object_id=object_id,
        reason=reason,
        message=message,
    )

    # Уведомляем администратора и всех модераторов
    god_username = getattr(settings, 'GOD_USERNAME', 'admin')
    target_type = "пост" if content_type_name == "post" else "комментарий"
    reason_label = dict(Complaint.Reason.choices).get(reason, reason)
    note_msg = f"Новая жалоба от @{request.user.username} на {target_type}: {reason_label}."
    note_link = "/accounts/complaints/"

    # Собираем получателей: god + все модераторы (кроме автора жалобы)
    from .models import Moderator, Notification
    from django.contrib.auth import get_user_model as gum
    UserModel = gum()

    mod_user_ids = set(Moderator.objects.values_list("user_id", flat=True).distinct())
    god_user_pk = UserModel.objects.filter(username=god_username).values_list("pk", flat=True).first()
    if god_user_pk:
        mod_user_ids.add(god_user_pk)
    # Исключаем автора жалобы
    mod_user_ids.discard(request.user.pk)

    if mod_user_ids:
        from accounts.notifications import notify
        for target_user in UserModel.objects.filter(pk__in=mod_user_ids):
            notify(
                target_user,
                Notification.Kind.COMPLAINT,
                note_msg,
                link=note_link,
            )

    messages.success(request, "Жалоба отправлена. Спасибо!")
    return redirect(request.META.get("HTTP_REFERER", "/"))


@login_required
@require_http_methods(["POST"])
def resolve_complaint(request, pk):
    """Отметить жалобу как решённую."""
    if not _can_handle_complaints(request.user):
        return HttpResponseForbidden("Доступ запрещён.")
    from .models import Complaint
    complaint = get_object_or_404(Complaint, pk=pk)
    complaint.status = Complaint.Status.RESOLVED
    complaint.resolved_by = request.user
    complaint.resolved_at = timezone.now()
    complaint.save(update_fields=["status", "resolved_by", "resolved_at"])
    messages.success(request, "Жалоба отмечена как решённая.")
    return redirect("complaints_list")


@login_required
@require_http_methods(["POST"])
def dismiss_complaint(request, pk):
    """Отклонить жалобу."""
    if not _can_handle_complaints(request.user):
        return HttpResponseForbidden("Доступ запрещён.")
    from .models import Complaint
    complaint = get_object_or_404(Complaint, pk=pk)
    complaint.status = Complaint.Status.DISMISSED
    complaint.resolved_by = request.user
    complaint.resolved_at = timezone.now()
    complaint.save(update_fields=["status", "resolved_by", "resolved_at"])
    messages.info(request, "Жалоба отклонена.")
    return redirect("complaints_list")
