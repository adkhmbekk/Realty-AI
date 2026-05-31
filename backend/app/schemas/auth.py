"""
Схемы для входа и профиля пользователя.
Схемы описывают, что приходит в запросе и что уходит в ответе.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TelegramAuthRequest(BaseModel):
    # Строка initData, которую Telegram передаёт в Mini App.
    init_data: str


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    is_owner: bool = False
    agency_id: Optional[int] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Активна ли подписка агентства.
    # Для суперадмина — None (у владельца платформы подписки нет, доступ всегда полный).
    subscription_active: Optional[bool] = None
    user: UserProfile
