from __future__ import annotations

from app.config import settings


def is_owner(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return str(user_id) in settings.owner_ids
