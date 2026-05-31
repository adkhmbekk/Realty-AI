"""
Схемы для агентств.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class AgencyCreate(BaseModel):
    name: str
    # Telegram ID человека, который станет админом этого агентства.
    admin_telegram_id: int
    admin_username: Optional[str] = None
    # На сколько дней открыть подписку при создании.
    subscription_days: int = 30


class AgencySubscriptionUpdate(BaseModel):
    # extend — продлить на N дней (и сделать активной);
    # set — задать дату окончания вручную (и активировать);
    # freeze — заморозить; activate — снова активировать.
    action: Literal["extend", "set", "freeze", "activate"]
    days: Optional[int] = 30
    # Для action="set": конкретная дата/время окончания подписки.
    expires_at: Optional[datetime] = None


class AgencyUpdate(BaseModel):
    # Переименование агентства.
    name: Optional[str] = None


class AgencyAdminUpdate(BaseModel):
    # Назначить/сменить администратора агентства (по Telegram ID).
    admin_telegram_id: int
    admin_username: Optional[str] = None


class AgencySettingsOut(BaseModel):
    # Настройки агентства, доступные его сотрудникам.
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    project_name: Optional[str] = None
    status: str
    subscription_expires_at: Optional[datetime] = None
    timezone: str
    default_currency: str


class AgencySettingsUpdate(BaseModel):
    # Что админ агентства может менять в настройках.
    project_name: Optional[str] = None
    timezone: Optional[str] = None
    default_currency: Optional[str] = None


class AgencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    project_name: Optional[str] = None
    status: str
    subscription_expires_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    created_at: datetime
    # Текущий администратор агентства (для панели суперадмина).
    # Заполняется сервисом; в самой модели Agency этих полей нет.
    admin_telegram_id: Optional[int] = None
    admin_name: Optional[str] = None
