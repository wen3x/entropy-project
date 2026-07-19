def allow_like(user_id: int) -> bool:
    """Лайки не имеют rate limit — всегда разрешены."""
    return True
