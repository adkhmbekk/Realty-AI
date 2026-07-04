"""
Схемы для агентств.
"""
from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgencyCreate(BaseModel):
    name: str = Field(max_length=120)
    # Telegram ID человека, который станет админом этого агентства.
    admin_telegram_id: int
    admin_username: Optional[str] = Field(default=None, max_length=64)
    # На сколько дней открыть подписку при создании.
    subscription_days: int = Field(default=30, ge=1, le=3650)
    # Необязательный телефон человека, открывшего агентство (можно указать позже).
    client_phone: Optional[str] = Field(default=None, max_length=64)


class PersonalAgencyCreate(BaseModel):
    # Личное агентство владельца платформы: нужно только название. Админ —
    # сам владелец (через acting-контекст), подписки нет.
    name: str = Field(max_length=120)


class AgencyRegister(BaseModel):
    # Самостоятельная регистрация агентства (человек открывает бот без агентства
    # и создаёт своё). Личность подтверждается подписью Telegram (init_data).
    init_data: str
    name: str = Field(max_length=120)
    owner_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=64)


class OpenAgencyCreate(BaseModel):
    # Открыть ЕЩЁ ОДНО своё агентство (для уже действующего участника). Нужны
    # только название и (необязательно) телефон — человек станет владельцем.
    name: str = Field(max_length=120)
    phone: Optional[str] = Field(default=None, max_length=64)


class AgencyDraftCreate(BaseModel):
    # Создание агентства «по ссылке»: ID админа НЕ нужен — кто откроет ссылку
    # активации, тот и станет главным админом. Подписка стартует с активации.
    name: str = Field(max_length=120)
    subscription_days: int = Field(default=30, ge=1, le=3650)
    client_phone: Optional[str] = Field(default=None, max_length=64)


class ActivationOut(BaseModel):
    # Ссылка-активация агентства (для владельца платформы).
    code: str
    link: Optional[str] = None
    expires_at: datetime
    # active (действует) / expired (истекла) / used (уже активировано).
    status: str


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
    # Переименование агентства и/или правка телефона открывшего агентство.
    name: Optional[str] = Field(default=None, max_length=120)
    # Телефон человека, открывшего агентство. Пустая строка очищает поле.
    client_phone: Optional[str] = Field(default=None, max_length=64)


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
    # Тариф агентства (сейчас у всех бесплатный 'start'). Подписка отключена.
    tariff: str = "start"
    subscription_expires_at: Optional[datetime] = None
    timezone: str
    default_currency: str
    # Общее агентство платформы («Realty AI»): новые объекты по умолчанию идут в
    # общую базу МЛС (галочку можно снять). Форма объекта смотрит на этот флаг.
    is_shared: bool = False
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
    # Тариф агентства (сейчас у всех бесплатный 'start').
    tariff: str = "start"
    subscription_expires_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    created_at: datetime
    # Личное агентство владельца платформы (если задано — это «моё» агентство).
    owner_telegram_id: Optional[int] = None
    # Общее агентство платформы («Realty AI»): в него входят все владельцы.
    is_shared: bool = False
    # Телефон человека, открывшего агентство (необязательный, виден суперадмину).
    client_phone: Optional[str] = None
    # Текущий администратор агентства (для панели суперадмина).
    # Заполняется сервисом; в самой модели Agency этих полей нет.
    admin_telegram_id: Optional[int] = None
    admin_name: Optional[str] = None


class AgencyDraftOut(BaseModel):
    # Результат создания черновика: само агентство + ссылка для активации.
    agency: AgencyOut
    activation: ActivationOut


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
    # Присутствие «в сети»: время последнего heartbeat + флаг онлайн.
    last_seen_at: Optional[datetime] = None
    online: bool = False
    added: int = 0
    # Сделки/комиссия сотрудника (Волна 7). commission — по валютам {USD: ...}.
    deals_won: int = 0
    commission: Dict[str, float] = {}


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
    # Разбивка «из каналов»: массовый импорт (bulk) и авто-импорт (auto).
    added_bulk: int = 0
    added_auto: int = 0
    # Активность команды.
    logins_7d: int = 0
    logins_30d: int = 0
    active_users: int = 0
    total_users: int = 0
    # Сколько сотрудников сейчас «в сети» (по heartbeat).
    online_users: int = 0
    last_activity_at: Optional[datetime] = None
    # Сделки и комиссия агентства (Волна 7).
    clients_total: int = 0
    deals_total: int = 0
    deals_active: int = 0
    deals_won: int = 0
    # Комиссия по валютам со сделок «деньги» (задаток+): {"USD": 5000, "UZS": ...}.
    revenue: Dict[str, float] = {}
    employees: List[EmployeeActivityOut] = []
