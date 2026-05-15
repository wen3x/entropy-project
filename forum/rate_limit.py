from django.contrib import messages
from django.core.cache import cache


def allow_like(user_id: int) -> bool:
    key = f"entropy:like_rl:{user_id}"
    if cache.get(key):
        return False
    cache.set(key, 1, timeout=1)
    return True


def deny_like_message(request):
    messages.error(request, "Слишком быстро: не более одного лайка в секунду.")
