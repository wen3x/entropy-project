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
        "code": "profile-color-ice",
        "title": "Тема «Ледяное сияние»",
        "description": "Голубой цвет профиля и подсветка ника.",
        "price_tokens": 500,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_BASIC,
        "sort_order": 2,
    },
    {
        "code": "profile-color-matrix",
        "title": "Тема «Матрица»",
        "description": "Зелёный цвет профиля и подсветка ника.",
        "price_tokens": 500,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_BASIC,
        "sort_order": 3,
    },
    {
        "code": "profile-color-sunset",
        "title": "Тема «Закат энтропии»",
        "description": "Оранжевый цвет профиля и подсветка ника.",
        "price_tokens": 500,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_BASIC,
        "sort_order": 4,
    },
    {
        "code": "profile-color-gold",
        "title": "Тема «Золотой»",
        "description": "Золотой цвет профиля с мягким свечением ника.",
        "price_tokens": 1000,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_GOLD,
        "sort_order": 5,
    },
)

# Маппинг кода товара → цвет профиля
COLOR_CODE_MAP = {
    "profile-color-ice": "ice",
    "profile-color-matrix": "matrix",
    "profile-color-sunset": "sunset",
    "profile-color-gold": "gold",
}

COLOR_NAMES = {
    "ice": "Ледяное сияние",
    "matrix": "Матрица",
    "sunset": "Закат энтропии",
    "gold": "Золотой",
    "red": "Красный",
    "blue": "Синий",
    "green": "Зелёный",
}


def ensure_default_shop_items():
    for data in DEFAULT_SHOP_ITEMS:
        ShopItem.objects.update_or_create(code=data["code"], defaults=data)
    # Скрываем старый объединённый товар, если он ещё есть
    ShopItem.objects.filter(code="profile-color-basic").update(visible_in_shop=False)


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

        # Цвета профиля: определяем цвет по коду товара
        target_color = COLOR_CODE_MAP.get(item.code)
        if not target_color:
            return False, "Неизвестный товар."

        owned = locked.owned_colors_list

        if target_color in owned:
            # Уже куплено — просто активируем
            User.objects.filter(pk=locked.pk).update(profile_color=target_color)
            color_name = COLOR_NAMES.get(target_color, target_color)
            return True, f"Тема «{color_name}» активирована."

        if locked.tokens < item.price_tokens:
            return False, "Недостаточно токенов."

        new_owned = list(set(owned + [target_color]))
        color_name = COLOR_NAMES.get(target_color, target_color)
        User.objects.filter(pk=locked.pk).update(
            tokens=F("tokens") - item.price_tokens,
            owned_colors=new_owned,
            profile_color=target_color,
        )
        return True, f"Тема «{color_name}» приобретена и активирована."

    return False, "Неизвестный тип товара."


def reset_theme(user: User) -> tuple[bool, str]:
    User.objects.filter(pk=user.pk).update(profile_color="")
    return True, "Тема профиля сброшена до стандартной."
