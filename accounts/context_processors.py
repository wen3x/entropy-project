from django.conf import settings


def site_context(request):
    is_god = (
        request.user.is_authenticated and request.user.username == "wen3x"
    )
    unread_notifications = 0
    if request.user.is_authenticated:
        from accounts.models import Notification

        unread_notifications = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
    return {
        "is_god": is_god,
        "unread_notifications": unread_notifications,
        "donation_alerts_url": settings.DONATION_ALERTS_URL,
    }
