import random

from django import template

register = template.Library()

CORRUPT_SYMBOLS = "@#$%&"


@register.filter
def corrupt_title(value: str) -> str:
    """~30% букв заменяются на символы распада."""
    if not value:
        return value
    chars = list(value)
    letter_indices = [i for i, c in enumerate(chars) if c.isalpha()]
    if not letter_indices:
        return value
    count = max(1, int(len(letter_indices) * 0.3))
    for idx in random.sample(letter_indices, min(count, len(letter_indices))):
        chars[idx] = random.choice(CORRUPT_SYMBOLS)
    return "".join(chars)
