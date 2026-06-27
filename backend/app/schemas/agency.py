"""
Схемы для агентств.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgencyCreate(BaseModel):
    name: str = Field(max_length=120)
    # Telegram ID человека, который станет админом этого агентства.
    admin_telegram_id: int
    admin_username: Optional[str] = Field(default=None, max_length=64)
    # На сколько дней открыть подписку при создании.
    subscription_days: int = Field(default=30, ge=1, le=3650)


class PersonalAgencyCreate(BaseModel):
    # Личное агентство владельца платформы: нужно только название. Админ —
    # сам владелец (через acting-контекст), подписки нет.
    name: str = Field(max_length=120)


class AgencySubscriptionUpdate(BaseModel):
    # extend — продлить на N дней (и сделать активной);
    # set — задать дату окончания вручную (и активировать);
    # freeze — заморозить; activate — снова активировать.
    action: Literal["extend", "set", "freeze", "activate"]
    days: Optional[int] = Field(default=30, ge=1, le=3650)
    # Для action="set": конкретная дата/время окончания подписки.
    expires_at: Optional[datetime] = None
    # Необязательные данные платежа (для истории): сумма, валюта, способ, заметка.
    amount: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, max_length=8)
    method: Optional[str] = Field(default=None, max_length=60)
    note: Optional[str] = Field(default=None, max_length=500)


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
    name: Optional[str] = Field(default=None, max_length=120)


class AgencyAdminUpdate(BaseModel):
    # Назначить/сменить администратора агентства (по Telegram ID).
    admin_telegram_id: int
    admin_username: Optional[str] = Field(default=None, max_length=64)


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
    # Контакт поддержки платформы (общий для всех агентств): ссылка на Telegram,
    # открывается кнопкой «Поддержка» в приложении. Берётся из настройки SUPPORT_URL.
    support_url: Optional[str] = None


class AgencySettingsUpdate(BaseModel):
    # Что админ агентства может менять в настройках.
    project_name: Optional[str] = Field(default=None, max_length=120)
    timezone: Optional[str] = Field(default=None, max_length=64)
    default_currency: Optional[str] = Field(default=None, max_length=8)
    # Контактный номер агентства (номер главного админа для клиентов).
    contact_phone: Optional[str] = Field(default=None, max_length=64)


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


# ── Наблюдение за агентствами (использование) ────────────────────────
# Уровень вовлечённости (engagement): active / quiet / asleep / new — «светофор».
class AgencyUsageOut(BaseModel):
    """Компактная сводка использования агентства (для списка агентств)."""
    agency_id: int
    objects_total: int = 0
    added_today: int = 0
    added_7d: int = 0
    added_30d: int = 0
    logins_7d: int = 0
    active_users: int = 0
    total_users: int = 0
    last_activity_at: Optional[datetime] = None
    engagement: str = "new"


class DailyCountOut(BaseModel):
    # Дата (YYYY-MM-DD, в часовом поясе агентства) и сколько объектов добавлено.
    date: str
    added: int


class EmployeeActivityOut(BaseModel):
    user_id: Optional[int] = None
    name: Optional[str] = None
    last_login_at: Optional[datetime] = None
    added: int = 0


class AgencyActivityOut(BaseModel):
    """Подробный отчёт об активности агентства (карточка агентства)."""
    objects_total: int = 0
    # Объекты по статусам и типам сделки.
    active: int = 0
    deposit: int = 0
    sold: int = 0
    rented: int = 0
    sale: int = 0
    rent: int = 0
    # Добавлено объектов: по дням (для нового агентства — главное).
    added_today: int = 0
    added_yesterday: int = 0
    added_2d: int = 0
    added_7d: int = 0
    added_30d: int = 0
    daily: List[DailyCountOut] = []
    # Как добавляют: вручную / по ссылке (площадка) / из Telegram-канала.
    source_manual: int = 0
    source_link: int = 0
    source_channel: int = 0
    # Активность команды.
    logins_7d: int = 0
    logins_30d: int = 0
    active_users: int = 0
    total_users: int = 0
    last_activity_at: Optional[datetime] = None
    employees: List[EmployeeActivityOut] = []
