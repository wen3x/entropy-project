from datetime import timedelta
from django.conf import settings


def site_context(request):
    """Глобальный контекст для всех шаблонов: admin, модератор, уведомления, бан, донаты."""
    god_username = getattr(settings, 'GOD_USERNAME', 'admin')
    is_god = (
        request.user.is_authenticated and request.user.username == god_username
    )
    is_moderator = False
    unread_notifications = 0
    active_ban = None
    if request.user.is_authenticated:
        from accounts.models import Ban, Moderator, Notification

        if not is_god:
            is_moderator = Moderator.objects.filter(user=request.user).exists()

        unread_notifications = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
        try:
            from django.utils import timezone
            ban = Ban.objects.filter(
                user=request.user,
                expires_at__gt=timezone.now(),
                node__isnull=True,
            ).first()
            if ban:
                active_ban = ban
        except Exception:
            pass

    email_available = bool(getattr(settings, 'EMAIL_HOST', ''))

    # ── Recent posts for the right column ──
    recent_posts = []
    if request.user.is_authenticated or True:  # always fetch for all users
        try:
            from django.utils import timezone
            from forum.models import Post
            now = timezone.now()
            cutoff = now - timedelta(hours=24)
            recent_posts = list(
                Post.objects.filter(is_active=True, expires_at__gt=now, created_at__gte=cutoff)
                .select_related("author", "node")
                .order_by("-created_at")[:15]
            )
        except Exception:
            recent_posts = []

    return {
        "is_god": is_god,
        "is_moderator": is_moderator,
        "god_username": god_username,
        "unread_notifications": unread_notifications,
        "donation_alerts_url": settings.DONATION_ALERTS_URL,
        "active_ban": active_ban,
        "recaptcha_site_key": getattr(settings, 'RECAPTCHA_SITE_KEY', ''),
        "email_available": email_available,
        "recent_posts": recent_posts,
    }
