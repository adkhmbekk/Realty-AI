"""
Схемы управления командой агентства (просмотр сотрудников, вкл/выкл доступа).
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # None у нативных юзеров (вход Google/Apple без Telegram) — иначе сериализация
    # члена команды падает валидацией ответа.
    telegram_id: Optional[int] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    is_owner: bool = False
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class MemberUpdate(BaseModel):
    # Активность (доступ) сотрудника.
    is_active: Optional[bool] = None
    # Роль сотрудника внутри агентства: "agency_admin" или "agent".
    # Менять на "superadmin" нельзя — это владелец платформы, не сотрудник.
    role: Optional[str] = None


class MemberAuditOut(BaseModel):
    # Запись журнала действий по агентству (для администратора).
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    actor_name: Optional[str] = None
    target: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime
