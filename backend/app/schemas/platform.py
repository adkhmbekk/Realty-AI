"""
Схемы для эндпоинтов уровня платформы.
"""
from typing import Optional

from pydantic import BaseModel


class SuperadminTransfer(BaseModel):
    # Telegram ID человека, которому передаётся роль владельца платформы.
    new_telegram_id: int
    new_username: Optional[str] = None
