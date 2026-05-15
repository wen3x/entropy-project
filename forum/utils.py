import secrets
import string

SLUG_ALPHABET = string.ascii_letters + string.digits + "_"


def generate_post_slug(length: int | None = None) -> str:
    """Уникальный код поста: 8–11 символов [a-zA-Z0-9_]."""
    from .models import Post

    if length is None:
        length = secrets.randbelow(4) + 8
    length = max(8, min(11, length))
    while True:
        slug = "".join(secrets.choice(SLUG_ALPHABET) for _ in range(length))
        if not Post.objects.filter(slug=slug).exists():
            return slug
