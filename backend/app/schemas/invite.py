"""
Схемы приглашений сотрудников.

- InviteCreate — что присылает админ при создании приглашения;
- InviteOut    — что отдаём (код, ссылка, роль, срок, статус);
- InviteRedeem — что присылает новый сотрудник, чтобы вступить (его initData
  от Telegram + код приглашения).
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

# Роли, которые можно выдать через приглашение.
ALLOWED_INVITE_ROLES = ("agent", "agency_admin")


class InviteCreate(BaseModel):
    # Какую роль получит приглашённый. По умолчанию — рядовой агент.
    role: str = "agent"
    # Через сколько дней приглашение перестанет действовать.
    expires_in_days: int = 7

    @field_validator("role")
    @classmethod
    def _check_role(cls, value: str) -> str:
        value = (value or "").strip()
        if value not in ALLOWED_INVITE_ROLES:
            raise ValueError(
                "Роль должна быть 'agent' (агент) или 'agency_admin' (администратор)."
            )
        return value

    @field_validator("expires_in_days")
    @classmethod
    def _check_days(cls, value: int) -> int:
        if value < 1 or value > 365:
            raise ValueError("Срок приглашения — от 1 до 365 дней.")
        return value


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    role: str
    # Статус: active (активно) / used (использовано) / expired (просрочено).
    status: str
    # Готовая ссылка-приглашение для Telegram (если задано имя бота), иначе null.
    join_link: Optional[str] = None
    expires_at: datetime
    used_at: Optional[datetime] = None
    used_by_telegram_id: Optional[int] = None
    created_at: datetime


class InviteRedeem(BaseModel):
    # initData от Telegram — подтверждает личность нового сотрудника.
    init_data: str
    # Код приглашения.
    code: str

    @field_validator("code")
    @classmethod
    def _strip_code(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("Код приглашения не может быть пустым.")
        return value
