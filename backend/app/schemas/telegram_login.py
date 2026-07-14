"""Схемы входа через Telegram-бота (start / poll)."""
from typing import Optional

from pydantic import BaseModel

from app.schemas.auth import AuthResponse


class TelegramStartResponse(BaseModel):
    # Одноразовый код и готовая ссылка t.me для открытия бота.
    code: str
    deep_link: str
    expires_in: int


class TelegramPollRequest(BaseModel):
    code: str


class TelegramPollResponse(BaseModel):
    # pending — ждём подтверждения; expired — код истёк/использован/отменён;
    # confirmed — вход подтверждён, auth содержит сессию.
    status: str
    auth: Optional[AuthResponse] = None
