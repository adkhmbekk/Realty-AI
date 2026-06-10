"""
Схемы для агентств.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict


class AgencyCreate(BaseModel):
    name: str
    # Telegram ID человека, который станет админом этого агентства.
    admin_telegram_id: int
    admin_username: Optional[str] = None
    # На сколько дней открыть подписку при создании.
    subscription_days: int = 30


class PersonalAgencyCreate(BaseModel):
    # Личное агентство владельца платформы: нужно только название. Админ —
    # сам владелец (через acting-контекст), подписки нет.
    name: str


class AgencySubscriptionUpdate(BaseModel):
    # extend — продлить на N дней (и сделать активной);
    # set — задать дату окончания вручную (и активировать);
    # freeze — заморозить; activate — снова активировать.
    action: Literal["extend", "set", "freeze", "activate"]
    days: Optional[int] = 30
    # Для action="set": конкретная дата/время окончания подписки.
    expires_at: Optional[datetime] = None
    # Необязательные данные платежа (для истории): сумма, валюта, способ, заметка.
    amount: Optional[float] = None
    currency: Optional[str] = None
    method: Optional[str] = None
    note: Optional[str] = None


class AgencyPaymentOut(BaseModel):
    # Запись истории платежей/продлений подписки.
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    days: Optional[int] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    method: Optional[str] = None
    note: Optional[str] = None
    expires_at_after: Optional[datetime] = None
    created_by_telegram_id: Optional[int] = None
    created_at: datetime


class CurrencyTotalOut(BaseModel):
    # Итог по одной валюте.
    currency: str
    amount: float
    count: int


class PaymentsSummaryOut(BaseModel):
    # Свод платежей по всем агентствам (для владельца платформы).
    all_time: List[CurrencyTotalOut]
    this_month: List[CurrencyTotalOut]
    total_records: int


class AgencyAuditOut(BaseModel):
    # Запись журнала аудита (для панели суперадмина).
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    actor_name: Optional[str] = None
    actor_telegram_id: Optional[int] = None
    target: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime


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
    # Контактный номер агентства (подставляется при «поделиться» вместо
    # номера собственника). Виден сотрудникам, чтобы понимать, что уйдёт клиенту.
    contact_phone: Optional[str] = None
    # Telegram-логин владельца агентства (@username), показывается клиентам в карточке.
    contact_username: Optional[str] = None


class AgencySettingsUpdate(BaseModel):
    # Что админ агентства может менять в настройках.
    project_name: Optional[str] = None
    timezone: Optional[str] = None
    default_currency: Optional[str] = None
    # Контактный номер агентства (номер главного админа для клиентов).
    contact_phone: Optional[str] = None


class AgencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    project_name: Optional[str] = None
    status: str
    subscription_expires_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    created_at: datetime
    # Личное агентство владельца платформы (если задано — это «моё» агентство).
    owner_telegram_id: Optional[int] = None
    # Текущий администратор агентства (для панели суперадмина).
    # Заполняется сервисом; в самой модели Agency этих полей нет.
    admin_telegram_id: Optional[int] = None
    admin_name: Optional[str] = None
