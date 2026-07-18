import re
import random

from django import template
from django.urls import reverse
from django.contrib.auth import get_user_model

register = template.Library()


@register.filter
def corrupt_title(value):
    """Заменяет ~30% букв в строке на символы @#$%& (для кладбища)."""
    if not value:
        return value
    symbols = "@#$%&"
    result = []
    for ch in value:
        if ch.isalpha() and random.random() < 0.3:
            result.append(random.choice(symbols))
        else:
            result.append(ch)
    return "".join(result)


@register.filter
def mention_links(text):
    """Превращает @username в ссылку на профиль /u/@username/"""
    if not text:
        return text

    def replace_mention(match):
        username = match.group(1)
        User = get_user_model()
        if User.objects.filter(username__iexact=username).exists():
            url = reverse("profile_detail", kwargs={"username": username})
            return f'<a href="{url}" class="mention">@{username}</a>'
        return match.group(0)

    # (?<!\w) — не цепляем email: user@example.com
    return re.sub(r"(?<!\w)@(\w+)", replace_mention, text)
