from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import ShopItem, User

DEFAULT_SHOP_ITEMS = (
    {
        "code": "vitality-month",
        "title": "Продлить жизнь аккаунта (мес.)",
        "description": "Добавляет 30 дней к сроку жизни аккаунта.",
        "price_tokens": 100,
        "item_type": ShopItem.ItemType.EXTEND_VITALITY,
        "sort_order": 1,
    },
    {
        "code": "profile-color-basic",
        "title": "Цвет профиля (темы)",
        "description": "Разблокирует темы: Ледяное сияние, Матрица, Закат энтропии. После покупки переключать их можно бесплатно.",
        "price_tokens": 500,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_BASIC,
        "sort_order": 2,
    },
    {
        "code": "profile-color-gold",
        "title": "Цвет профиля (ЗОЛОТОЙ)",
        "description": "Разблокирует золотой цвет профиля с мягким свечением ника. После покупки активировать можно бесплатно.",
        "price_tokens": 1000,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_GOLD,
        "sort_order": 3,
    },
)

BASIC_COLORS = frozenset({"ice", "matrix", "sunset"})


def ensure_default_shop_items():
    for data in DEFAULT_SHOP_ITEMS:
        ShopItem.objects.update_or_create(code=data["code"], defaults=data)


def get_visible_shop_items():
    ensure_default_shop_items()
    return ShopItem.objects.filter(visible_in_shop=True)


def purchase_item(user: User, item: ShopItem, color: str = "") -> tuple[bool, str]:
    if not item.visible_in_shop:
        return False, "Товар недоступен в магазине."

    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)

        if item.item_type == ShopItem.ItemType.EXTEND_VITALITY:
            if locked.tokens < item.price_tokens:
                return False, "Недостаточно токенов."
            User.objects.filter(pk=locked.pk).update(
                tokens=F("tokens") - item.price_tokens,
                vitality_expires_at=F("vitality_expires_at") + timedelta(days=30),
            )
            return True, "Срок жизни аккаунта продлён на 30 дней."

        if item.item_type == ShopItem.ItemType.PROFILE_COLOR_BASIC:
            if color not in BASIC_COLORS:
                return False, "Выберите тему: ice (Ледяное сияние), matrix (Матрица), sunset (Закат энтропии)."
            if locked.has_basic_colors:
                User.objects.filter(pk=locked.pk).update(profile_color=color)
                return True, f"Цвет профиля изменён."
            if locked.tokens < item.price_tokens:
                return False, "Недостаточно токенов."
            User.objects.filter(pk=locked.pk).update(
                tokens=F("tokens") - item.price_tokens,
                has_basic_colors=True,
                profile_color=color,
            )
            return True, "Базовые цвета профиля разблокированы. Теперь переключать их можно бесплатно."

        if item.item_type == ShopItem.ItemType.PROFILE_COLOR_GOLD:
            if locked.has_gold_color:
                User.objects.filter(pk=locked.pk).update(profile_color=User.ProfileColor.GOLD)
                return True, "Золотой цвет профиля активирован."
            if locked.tokens < item.price_tokens:
                return False, "Недостаточно токенов."
            User.objects.filter(pk=locked.pk).update(
                tokens=F("tokens") - item.price_tokens,
                has_gold_color=True,
                profile_color=User.ProfileColor.GOLD,
            )
            return True, "Золотой цвет профиля разблокирован и активирован."

    return False, "Неизвестный тип товара."


def reset_theme(user: User) -> tuple[bool, str]:
    User.objects.filter(pk=user.pk).update(profile_color="")
    return True, "Тема профиля сброшена до стандартной."
