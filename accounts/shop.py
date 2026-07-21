from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import ShopItem, User

from .quests import on_shop_purchase, on_vitality_extend

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
        "description": "Голубой цвет профиля.",
        "price_tokens": 500,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_BASIC,
        "sort_order": 2,
    },
    {
        "code": "profile-color-matrix",
        "title": "Тема «Матрица»",
        "description": "Зелёный цвет профиля.",
        "price_tokens": 500,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_BASIC,
        "sort_order": 3,
    },
    {
        "code": "profile-color-sunset",
        "title": "Тема «Закат энтропии»",
        "description": "Оранжевый цвет профиля.",
        "price_tokens": 500,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_BASIC,
        "sort_order": 4,
    },
    {
        "code": "profile-color-red",
        "title": "Тема «Алый закат»",
        "description": "Красный цвет профиля.",
        "price_tokens": 500,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_BASIC,
        "sort_order": 5,
    },
    {
        "code": "profile-color-blue",
        "title": "Тема «Бездонная синева»",
        "description": "Синий цвет профиля.",
        "price_tokens": 500,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_BASIC,
        "sort_order": 6,
    },
    {
        "code": "profile-color-purple",
        "title": "Тема «Сиреневый туман»",
        "description": "Фиолетовый цвет профиля.",
        "price_tokens": 750,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_BASIC,
        "sort_order": 7,
    },
    {
        "code": "profile-color-pink",
        "title": "Тема «Неоновая роза»",
        "description": "Розовый цвет профиля.",
        "price_tokens": 750,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_BASIC,
        "sort_order": 8,
    },
    {
        "code": "profile-color-gray",
        "title": "Тема «Пепел эпохи»",
        "description": "Серый цвет профиля.",
        "price_tokens": 500,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_BASIC,
        "sort_order": 9,
    },
    {
        "code": "profile-color-metal",
        "title": "Тема «Жидкий металл»",
        "description": "Ярко-серый металлический цвет профиля.",
        "price_tokens": 750,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_BASIC,
        "sort_order": 10,
    },
    {
        "code": "profile-color-gold",
        "title": "Тема «Золотой»",
        "description": "Золотой цвет профиля с мягким свечением ника.",
        "price_tokens": 1000,
        "item_type": ShopItem.ItemType.PROFILE_COLOR_GOLD,
        "sort_order": 11,
    },
)

# Маппинг кода товара → цвет профиля
COLOR_CODE_MAP = {
    "profile-color-ice": "ice",
    "profile-color-matrix": "matrix",
    "profile-color-sunset": "sunset",
    "profile-color-gold": "gold",
    "profile-color-red": "red",
    "profile-color-blue": "blue",
    "profile-color-purple": "purple",
    "profile-color-pink": "pink",
    "profile-color-gray": "gray",
    "profile-color-metal": "metal",
}

COLOR_NAMES = {
    "ice": "Ледяное сияние",
    "matrix": "Матрица",
    "sunset": "Закат энтропии",
    "gold": "Золотой",
    "red": "Алый закат",
    "blue": "Бездонная синева",
    "purple": "Сиреневый туман",
    "pink": "Неоновая роза",
    "gray": "Пепел эпохи",
    "metal": "Жидкий металл",
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
    """Купить товар. Скидка берётся из discount_pct товара (устанавливается админом)."""
    if not item.visible_in_shop:
        return False, "Товар недоступен в магазине."

    discount_pct = item.discount_pct or 0
    if discount_pct < 0 or discount_pct > 100:
        discount_pct = 0

    final_price = max(0, int(item.price_tokens * (100 - discount_pct) / 100))

    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)

        if item.item_type == ShopItem.ItemType.EXTEND_VITALITY:
            if locked.tokens < final_price:
                return False, "Недостаточно токенов."
            User.objects.filter(pk=locked.pk).update(
                tokens=F("tokens") - final_price,
                vitality_expires_at=F("vitality_expires_at") + timedelta(days=30),
            )
            msg = "Срок жизни аккаунта продлён на 30 дней."
            if discount_pct:
                msg += f" (скидка {discount_pct}%)"
            # Квесты: Шопоголик + Живучий
            on_shop_purchase(user)
            on_vitality_extend(user)
            return True, msg

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

        if locked.tokens < final_price:
            return False, "Недостаточно токенов."

        new_owned = list(set(owned + [target_color]))
        color_name = COLOR_NAMES.get(target_color, target_color)
        User.objects.filter(pk=locked.pk).update(
            tokens=F("tokens") - final_price,
            owned_colors=new_owned,
            profile_color=target_color,
        )
        msg = f"Тема «{color_name}» приобретена и активирована."
        if discount_pct:
            msg += f" (скидка {discount_pct}%)"
        # Квест: Шопоголик (любая покупка)
        on_shop_purchase(user)
        return True, msg

    return False, "Неизвестный тип товара."


def reset_theme(user: User) -> tuple[bool, str]:
    User.objects.filter(pk=user.pk).update(profile_color="")
    return True, "Тема профиля сброшена до стандартной."
