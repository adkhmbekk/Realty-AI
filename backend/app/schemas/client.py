"""
Схемы клиентской базы: клиент, заявка («что ищет»), совпадение «заявка ↔ объект».

Критерии заявки зеркалят фильтры поиска объектов (см. schemas/apartment.py и
repositories/apartment_repo.search) — заявка по сути сохранённый поиск.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.apartment import ALLOWED_CURRENCIES, ApartmentOut, DealType


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
    status: str
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    # Заявки клиента (в детальной карточке). В списке — пусто для лёгкости.
    requests: List[RequestOut] = []
    # Сколько всего активных заявок и сколько новых совпадений (для списка).
    active_requests: int = 0
    new_match_count: int = 0


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
    apartment: ApartmentOut


class MatchSummaryOut(BaseModel):
    # Сколько новых совпадений видит текущий пользователь (для значка-счётчика).
    new_count: int


class ScanResultOut(BaseModel):
    # Сколько совпадений нашлось при подборе по существующей базе.
    found: int
