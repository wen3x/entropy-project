from django import template

from accounts.theme import PALETTES

register = template.Library()


@register.filter
def author_style(profile_color: str) -> str:
    palette = PALETTES.get(profile_color or "")
    if not palette:
        return ""
    color = palette["fg"]
    style = f"color:{color};font-weight:600"
    # Только золотая тема даёт свечение, остальные — только цвет
    if profile_color == "gold":
        glow = palette.get("glow", "")
        if glow:
            style += f";text-shadow:{glow}"
    return style


@register.filter
def profile_color_class(color: str) -> str:
    if not color:
        return ""
    return f"profile-color-{color}"
