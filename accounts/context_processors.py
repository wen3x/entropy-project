from django.conf import settings


def site_context(request):
    """Глобальный контекст для всех шаблонов: admin, уведомления, бан, донаты."""
    god_username = getattr(settings, 'GOD_USERNAME', 'admin')
    is_god = (
        request.user.is_authenticated and request.user.username == god_username
    )
    unread_notifications = 0
    active_ban = None
    if request.user.is_authenticated:
        from accounts.models import Ban, Notification

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

    return {
        "is_god": is_god,
        "unread_notifications": unread_notifications,
        "donation_alerts_url": settings.DONATION_ALERTS_URL,
        "active_ban": active_ban,
    }
