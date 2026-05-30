"""
Схемы для объектов недвижимости.

- ApartmentCreate — что присылают при создании объекта;
- ApartmentUpdate — что разрешено менять (белый список полей; статус и
  display_id здесь НЕ меняются — для статуса есть отдельные действия);
- ApartmentOut    — что отдаём в ответе (полная карточка);
- ApartmentListOut — страница списка с общим количеством (пагинация).
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator

# Допустимые статусы объекта (единый список для валидации).
ApartmentStatus = Literal["active", "deposit", "sold", "archived"]


# Поля, общие для создания и редактирования объекта.
class _ApartmentBase(BaseModel):
    name: Optional[str] = None
    # Агент-источник (id из справочника agents этого агентства).
    agent_id: Optional[int] = None
    phone: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    type: Optional[str] = None
    rooms: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    area: Optional[float] = None
    condition: Optional[str] = None
    furniture: Optional[str] = None
    appliances: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    description: Optional[str] = None

    @field_validator("rooms", "floor", "total_floors")
    @classmethod
    def _non_negative_int(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 0:
            raise ValueError("Значение не может быть отрицательным.")
        return value

    @field_validator("area", "price")
    @classmethod
    def _non_negative_num(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError("Значение не может быть отрицательным.")
        return value

    @field_validator("currency")
    @classmethod
    def _normalize_currency(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip().upper()
        return value or None


class ApartmentCreate(_ApartmentBase):
    """При создании все поля необязательны; display_id генерируется системой."""
    # Начальный статус объекта. По умолчанию — активный.
    status: Optional[ApartmentStatus] = None


class ApartmentUpdate(_ApartmentBase):
    """
    При редактировании меняем только переданные поля.
    Набор полей тот же, что и при создании (белый список) — статус и
    display_id менять через этот метод нельзя (для статуса есть отдельный метод).
    """


class ApartmentStatusUpdate(BaseModel):
    # Новый статус объекта: active / deposit (задаток) / sold / archived.
    status: ApartmentStatus


class ApartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_id: str
    status: str
    name: Optional[str] = None
    agent_id: Optional[int] = None
    phone: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    type: Optional[str] = None
    rooms: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    area: Optional[float] = None
    condition: Optional[str] = None
    furniture: Optional[str] = None
    appliances: Optional[str] = None
    price: Optional[float] = None
    currency: str
    description: Optional[str] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None


class ApartmentListOut(BaseModel):
    # Страница результатов поиска/списка.
    items: List[ApartmentOut]
    total: int
    limit: int
    offset: int
