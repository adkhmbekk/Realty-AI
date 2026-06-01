"""
Схемы для эндпоинтов уровня платформы.
"""
from typing import Optional

from pydantic import BaseModel


class SuperadminTransferRequest(BaseModel):
    # Шаг 1: запрос кода подтверждения (код придёт текущему владельцу в бот).
    new_telegram_id: int
    new_username: Optional[str] = None


class SuperadminTransfer(BaseModel):
    # Шаг 2: подтверждение передачи кодом из бота.
    # Telegram ID человека, которому передаётся роль владельца платформы.
    new_telegram_id: int
    new_username: Optional[str] = None
    code: str
