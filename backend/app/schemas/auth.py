"""
Схемы для входа и профиля пользователя.
Схемы описывают, что приходит в запросе и что уходит в ответе.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TelegramAuthRequest(BaseModel):
    # Строка initData, которую Telegram передаёт в Mini App.
    init_data: str


class RefreshRequest(BaseModel):
    # Долгоживущий refresh-пропуск, выданный при входе.
    refresh_token: str
    # Если суперадмин сейчас работает внутри своего личного агентства —
    # его id (чтобы тихое продление сессии не выкидывало из агентства).
    act_as_agency_id: Optional[int] = None


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    is_owner: bool = False
    agency_id: Optional[int] = None
    # Acting-контекст (суперадмин внутри своего личного агентства). У обычных
    # пользователей эти поля пустые. real_role показывает истинную роль, чтобы
    # UI знал, что под капотом владелец платформы, и показал кнопку «Выйти».
    acting_as_agency_id: Optional[int] = None
    acting_as_agency_name: Optional[str] = None
    real_role: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    # Долгоживущий пропуск для тихого обновления сессии (см. /auth/refresh).
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    # Активна ли подписка агентства.
    # Для суперадмина — None (у владельца платформы подписки нет, доступ всегда полный).
    subscription_active: Optional[bool] = None
    user: UserProfile
