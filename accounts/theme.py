PALETTES = {
    "default": {
        "fg": "var(--entropy-fg)",
        "fg_muted": "var(--entropy-fg-muted)",
        "fg_faint": "var(--entropy-fg-faint)",
        "fg_subtle": "var(--entropy-fg-subtle)",
        "on_accent": "var(--entropy-on-accent)",
    },
    "red": {
        "fg": "#e74c4c",
        "fg_muted": "rgba(231, 76, 76, 0.7)",
        "fg_faint": "rgba(231, 76, 76, 0.55)",
        "fg_subtle": "rgba(231, 76, 76, 0.45)",
        "on_accent": "#ffffff",
    },
    "blue": {
        "fg": "#4a8cff",
        "fg_muted": "rgba(74, 140, 255, 0.7)",
        "fg_faint": "rgba(74, 140, 255, 0.55)",
        "fg_subtle": "rgba(74, 140, 255, 0.45)",
        "on_accent": "#ffffff",
    },
    "green": {
        "fg": "#4caf78",
        "fg_muted": "rgba(76, 175, 120, 0.7)",
        "fg_faint": "rgba(76, 175, 120, 0.55)",
        "fg_subtle": "rgba(76, 175, 120, 0.45)",
        "on_accent": "#ffffff",
    },
    "gold": {
        "fg": "#e6c04a",
        "fg_muted": "rgba(230, 192, 74, 0.7)",
        "fg_faint": "rgba(230, 192, 74, 0.55)",
        "fg_subtle": "rgba(230, 192, 74, 0.45)",
        "on_accent": "#000000",
        "glow": "0 0 10px rgba(230, 192, 74, 0.55), 0 0 18px rgba(250, 204, 21, 0.35)",
    },
    "ice": {
        "fg": "#38bdf8",
        "fg_muted": "rgba(56, 189, 248, 0.7)",
        "fg_faint": "rgba(56, 189, 248, 0.55)",
        "fg_subtle": "rgba(56, 189, 248, 0.45)",
        "on_accent": "#000000",
    },
    "matrix": {
        "fg": "#4ade80",
        "fg_muted": "rgba(74, 222, 128, 0.7)",
        "fg_faint": "rgba(74, 222, 128, 0.55)",
        "fg_subtle": "rgba(74, 222, 128, 0.45)",
        "on_accent": "#000000",
    },
    "sunset": {
        "fg": "#f97316",
        "fg_muted": "rgba(249, 115, 22, 0.7)",
        "fg_faint": "rgba(249, 115, 22, 0.55)",
        "fg_subtle": "rgba(249, 115, 22, 0.45)",
        "on_accent": "#000000",
    },
    "purple": {
        "fg": "#a855f7",
        "fg_muted": "rgba(168, 85, 247, 0.7)",
        "fg_faint": "rgba(168, 85, 247, 0.55)",
        "fg_subtle": "rgba(168, 85, 247, 0.45)",
        "on_accent": "#ffffff",
    },
    "pink": {
        "fg": "#ec4899",
        "fg_muted": "rgba(236, 72, 153, 0.7)",
        "fg_faint": "rgba(236, 72, 153, 0.55)",
        "fg_subtle": "rgba(236, 72, 153, 0.45)",
        "on_accent": "#ffffff",
    },
    "gray": {
        "fg": "#9ca3af",
        "fg_muted": "rgba(156, 163, 175, 0.7)",
        "fg_faint": "rgba(156, 163, 175, 0.55)",
        "fg_subtle": "rgba(156, 163, 175, 0.45)",
        "on_accent": "#000000",
    },
    "metal": {
        "fg": "#d1d5db",
        "fg_muted": "rgba(209, 213, 219, 0.7)",
        "fg_faint": "rgba(209, 213, 219, 0.55)",
        "fg_subtle": "rgba(209, 213, 219, 0.45)",
        "on_accent": "#000000",
    },
}

# Site-wide light/dark themes (separate from profile PALETTES).
SITE_THEMES = ("light", "dark")


def get_palette(color_key: str) -> dict:
    if not color_key or color_key not in PALETTES:
        return PALETTES["default"]
    return PALETTES[color_key]


def get_theme_context(user) -> dict:
    if not user.is_authenticated:
        return {"theme_id": "default", "theme": PALETTES["default"]}
    color = user.profile_color or ""
    theme_id = color if color in PALETTES else "default"
    return {"theme_id": theme_id, "theme": get_palette(color)}
