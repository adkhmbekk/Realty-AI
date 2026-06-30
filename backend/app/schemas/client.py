"""
Схемы клиентской базы: клиент, заявка («что ищет»), совпадение «заявка ↔ объект».

Критерии заявки зеркалят фильтры поиска объектов (см. schemas/apartment.py и
repositories/apartment_repo.search) — заявка по сути сохранённый поиск.
"""
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.apartment import ALLOWED_CURRENCIES, ApartmentOut, DealType

# Приоритет клиента: горячий/тёплый/холодный («светофор» для агента).
Priority = Literal["hot", "warm", "cold"]


# ── Заявка («что ищет») ──────────────────────────────────────────────
class RequestCriteria(BaseModel):
    """Критерии заявки — зеркало фильтров поиска (можно несколько типов/районов)."""
    # Тип сделки: 'sale' (купить) или 'rent' (снять). По умолчанию — продажа.
    deal_type: Optional[DealType] = None
    types: Optional[List[str]] = None
    districts: Optional[List[str]] = None
    rooms_min: Optional[int] = None
    rooms_max: Optional[int] = None
    floor_min: Optional[int] = None
    floor_max: Optional[int] = None
    land_area_min: Optional[float] = None
    land_area_max: Optional[float] = None
    # Площадь квартиры/дома в м² («квадратура»).
    area_min: Optional[float] = None
    area_max: Optional[float] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    currency: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("currency")
    @classmethod
    def _norm_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if not v:
            return None
        if v not in ALLOWED_CURRENCIES:
            raise ValueError("invalid_currency")
        return v

    @model_validator(mode="after")
    def _check_ranges(self):
        # Нижняя граница не может быть больше верхней (комнаты/этаж/сотки/цена).
        for lo, hi in (
            ("rooms_min", "rooms_max"),
            ("floor_min", "floor_max"),
            ("land_area_min", "land_area_max"),
            ("area_min", "area_max"),
            ("price_min", "price_max"),
        ):
            a, b = getattr(self, lo), getattr(self, hi)
            if a is not None and b is not None and a > b:
                raise ValueError("range_min_gt_max")
        return self


class RequestCreate(RequestCriteria):
    """Тело создания заявки (критерии)."""


class RequestUpdate(RequestCriteria):
    """Правка заявки. Дополнительно можно сменить статус (active/fulfilled/cancelled)."""
    status: Optional[str] = None


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    deal_type: str = "sale"
    types: Optional[List[str]] = None
    districts: Optional[List[str]] = None
    rooms_min: Optional[int] = None
    rooms_max: Optional[int] = None
    floor_min: Optional[int] = None
    floor_max: Optional[int] = None
    land_area_min: Optional[float] = None
    land_area_max: Optional[float] = None
    area_min: Optional[float] = None
    area_max: Optional[float] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    currency: Optional[str] = None
    note: Optional[str] = None
    status: str
    created_at: datetime
    # Сколько объектов уже подобрано по заявке (совпадения, кроме отклонённых).
    match_count: int = 0
    # Сколько из них новых (не просмотрены).
    new_match_count: int = 0


# ── Клиент ───────────────────────────────────────────────────────────
class ClientCreate(BaseModel):
    name: str = Field(max_length=120)
    last_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=64)
    note: Optional[str] = Field(default=None, max_length=2000)
    # Приоритет (hot/warm/cold) и источник (откуда пришёл) — оба необязательны.
    priority: Optional[Priority] = None
    source: Optional[str] = Field(default=None, max_length=120)
    # Необязательная первая заявка — создаётся вместе с клиентом (удобный путь
    # «запомнить для клиента» прямо из поиска).
    request: Optional[RequestCreate] = None

    @field_validator("name")
    @classmethod
    def _name_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("client_name_required")
        return v


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    last_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=64)
    note: Optional[str] = Field(default=None, max_length=2000)
    # Приоритет и источник (см. ClientCreate). None = «не менять»; ""/"none" = очистить.
    priority: Optional[str] = None
    source: Optional[str] = Field(default=None, max_length=120)
    # Приглушить уведомления по клиенту (Волна 8).
    muted: Optional[bool] = None
    # active / archived
    status: Optional[str] = None
    # Переназначить клиента другому агенту (только администратор).
    owner_id: Optional[int] = None


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    last_name: Optional[str] = None
    phone: Optional[str] = None
    note: Optional[str] = None
    priority: Optional[str] = None
    source: Optional[str] = None
    muted: bool = False
    status: str
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    # Заявки клиента (в детальной карточке). В списке — пусто для лёгкости.
    requests: List[RequestOut] = []
    # Сколько всего активных заявок и сколько новых совпадений (для списка).
    active_requests: int = 0
    new_match_count: int = 0
    # Сколько открытых задач у клиента (для значка в списке).
    open_tasks: int = 0


# ── Совпадение «заявка ↔ объект» ─────────────────────────────────────
class MatchOut(BaseModel):
    id: int
    status: str
    created_at: datetime
    request_id: int
    client_id: int
    client_name: str
    # Краткое человекочитаемое описание заявки («5 комн. · Юнусабад»).
    request_label: Optional[str] = None
    # Балл совпадения 0-100 (NULL у старых совпадений до Волны 1).
    score: Optional[int] = None
    # Причины совпадения и список «данные неполные» (поля объекта, не заполненные).
    match_good: List[str] = []
    match_missing: List[str] = []
    # MLS (Волна 9): own/mls; название агентства-владельца (для mls); «возможно дубль».
    source: str = "own"
    mls_agency: Optional[str] = None
    possible_dup: bool = False
    apartment: ApartmentOut


class MatchSummaryOut(BaseModel):
    # Сколько новых совпадений видит текущий пользователь (для значка-счётчика).
    new_count: int


class ScanResultOut(BaseModel):
    # Сколько совпадений нашлось при подборе по существующей базе.
    found: int


# ── Лента действий по клиенту (Волна 3) ──────────────────────────────
ActivityKind = Literal["call", "show", "meeting", "message", "note", "price_change"]


class ActivityCreate(BaseModel):
    kind: ActivityKind
    note: Optional[str] = Field(default=None, max_length=2000)


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    note: Optional[str] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime


# ── Задачи по клиенту (Волна 4) ──────────────────────────────────────
class TaskCreate(BaseModel):
    title: str = Field(max_length=300)
    deadline: Optional[date] = None

    @field_validator("title")
    @classmethod
    def _title_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("task_title_required")
        return v


class TaskUpdate(BaseModel):
    status: Literal["open", "done"]


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    client_id: int
    title: str
    deadline: Optional[date] = None
    status: str
    kind: str
    created_at: datetime
    # Для списка «мои задачи» — имя клиента (заполняет сервис).
    client_name: Optional[str] = None


# ── Сделки и комиссия (Волна 5) ──────────────────────────────────────
DealStage = Literal[
    "new", "interested", "shown", "price_agreed", "deposit", "contract", "sold", "cancelled",
]


def _norm_deal_currency(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip().upper()
    if not v:
        return None
    if v not in ALLOWED_CURRENCIES:
        raise ValueError("invalid_currency")
    return v


class DealCreate(BaseModel):
    apartment_id: Optional[int] = None
    stage: DealStage = "new"
    # Цена и комиссия не могут быть отрицательными (фикс аудита #6).
    price: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    commission: Optional[float] = Field(default=None, ge=0)
    commission_currency: Optional[str] = None
    agent_id: Optional[int] = None
    note: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("currency", "commission_currency")
    @classmethod
    def _cur(cls, v: Optional[str]) -> Optional[str]:
        return _norm_deal_currency(v)


class DealUpdate(BaseModel):
    stage: Optional[DealStage] = None
    apartment_id: Optional[int] = None
    price: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = None
    commission: Optional[float] = Field(default=None, ge=0)
    commission_currency: Optional[str] = None
    agent_id: Optional[int] = None
    note: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("currency", "commission_currency")
    @classmethod
    def _cur(cls, v: Optional[str]) -> Optional[str]:
        return _norm_deal_currency(v)


class DealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    client_id: int
    client_name: Optional[str] = None
    apartment_id: Optional[int] = None
    apartment_label: Optional[str] = None
    stage: str
    price: Optional[float] = None
    currency: Optional[str] = None
    commission: Optional[float] = None
    commission_currency: Optional[str] = None
    agent_id: Optional[int] = None
    agent_name: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime
    closed_at: Optional[datetime] = None


# ── ИИ-подсказки по правилам (Волна 6) ───────────────────────────────
class HintOut(BaseModel):
    # kind: silent / new_matches / total_matches / no_request
    kind: str
    count: Optional[int] = None
    days: Optional[int] = None


# ── Настройка уведомлений (Волна 8) ──────────────────────────────────
class NotifyPrefIn(BaseModel):
    match_notify: Literal["off", "instant", "daily"]


# ── Сводка по клиентам/сделкам для дашборда (Волна 7) ─────────────────
class ClientStatsOut(BaseModel):
    clients: int = 0          # всего активных клиентов (агенту — свои, админу — все)
    in_search: int = 0        # клиенты с активной заявкой («в поиске»)
    deals_active: int = 0     # сделки в работе (не продано/не отменено)
    deals_won: int = 0        # сделки «Продано»
