"""
Схемы для объектов недвижимости.

- ApartmentCreate — что присылают при создании объекта;
- ApartmentUpdate — что разрешено менять (белый список полей; статус и
  display_id здесь НЕ меняются — для статуса есть отдельные действия);
- ApartmentOut    — что отдаём в ответе (полная карточка);
- ApartmentShareOut — что отдаём при «поделиться» (без номера собственника и комментария);
- ApartmentListOut — страница списка с общим количеством (пагинация);
- ApartmentStatsOut — мини-статистика по статусам;
- ApartmentEventOut — запись журнала действий.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator

# Допустимые статусы объекта (единый список для валидации).
ApartmentStatus = Literal["active", "deposit", "sold"]

# Допустимые значения поля «мебель и техника».
FurnitureAppliances = Literal[
    "furniture_and_appliances", "furniture_only", "appliances_only", "none"
]


# Поля, общие для создания и редактирования объекта.
class _ApartmentBase(BaseModel):
    name: Optional[str] = None
    # Номер собственника (конфиденциально — виден только команде).
    owner_phone: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    type: Optional[str] = None
    rooms: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    area: Optional[float] = None
    # Площадь участка в сотках (для типа «Участок»).
    land_area: Optional[float] = None
    condition: Optional[str] = None
    # Мебель и техника (один параметр с вариантами).
    furniture_appliances: Optional[FurnitureAppliances] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    description: Optional[str] = None
    # Внутренний комментарий (не виден при шаринге).
    comment: Optional[str] = None
    # Ссылка на фото объекта.
    photo_url: Optional[str] = None
    # Ссылка на источник (OLX, Telegram и т.д.).
    source_link: Optional[str] = None
    # Источник — название канала/площадки (внутреннее, не уходит клиенту).
    source: Optional[str] = None

    @field_validator("rooms", "floor", "total_floors")
    @classmethod
    def _non_negative_int(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 0:
            raise ValueError("value_negative")
        return value

    @field_validator("area", "land_area", "price")
    @classmethod
    def _non_negative_num(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError("value_negative")
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
    # Новый статус объекта: active / deposit (задаток) / sold.
    status: ApartmentStatus


class ApartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_id: str
    status: str
    name: Optional[str] = None
    owner_phone: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    type: Optional[str] = None
    rooms: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    area: Optional[float] = None
    land_area: Optional[float] = None
    condition: Optional[str] = None
    furniture_appliances: Optional[str] = None
    price: Optional[float] = None
    currency: str
    description: Optional[str] = None
    comment: Optional[str] = None
    photo_url: Optional[str] = None
    source_link: Optional[str] = None
    source: Optional[str] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None
    # Когда объект перемещён в архив (мягкое удаление). NULL — в базе.
    deleted_at: Optional[datetime] = None


class ApartmentShareOut(BaseModel):
    """
    Карточка объекта для отправки третьим лицам.
    Без номера собственника (owner_phone) и без комментария (comment).
    Вместо номера собственника — контактный телефон главного админа агентства.
    """
    display_id: str
    status: str
    name: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    type: Optional[str] = None
    rooms: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    area: Optional[float] = None
    land_area: Optional[float] = None
    condition: Optional[str] = None
    furniture_appliances: Optional[str] = None
    price: Optional[float] = None
    currency: str
    description: Optional[str] = None
    photo_url: Optional[str] = None
    source_link: Optional[str] = None
    # Контактный телефон агентства (номер главного админа).
    contact_phone: Optional[str] = None
    contact_username: Optional[str] = None
    # Текстовое представление карточки для копирования/отправки.
    share_text: str


class ApartmentListOut(BaseModel):
    # Страница результатов поиска/списка.
    items: List[ApartmentOut]
    total: int
    limit: int
    offset: int


class DuplicateGroupOut(BaseModel):
    # Группа возможных дубликатов (объекты с одним номером собственника).
    key: str
    phone: Optional[str] = None
    count: int
    items: List[ApartmentOut]


class DuplicateDismissIn(BaseModel):
    # Подтвердить, что группа (по ключу) — НЕ дубликаты.
    key: str


class ApartmentStatsOut(BaseModel):
    # Мини-статистика по объектам агентства.
    active: int
    deposit: int
    sold: int
    total: int


class ApartmentEventOut(BaseModel):
    # Запись журнала действий по объекту.
    action: str
    note: Optional[str] = None
    user_name: Optional[str] = None
    created_at: datetime



class AgentActivityOut(BaseModel):
    # Активность одного сотрудника: сколько объектов добавил и сколько продано.
    user_id: Optional[int] = None
    name: Optional[str] = None
    total: int
    sold: int


class ApartmentAnalyticsOut(BaseModel):
    # Аналитика для руководителя агентства.
    active: int
    deposit: int
    sold: int
    total: int
    added_this_month: int
    sold_this_month: int
    agents: List[AgentActivityOut]


class ShareResultOut(BaseModel):
    # Результат отправки объекта через бота.
    ok: bool
    photos: int



class TimeseriesPointOut(BaseModel):
    label: str
    added: int
    sold: int


class TimeseriesOut(BaseModel):
    period: str
    buckets: List[TimeseriesPointOut]


class AgentEventOut(BaseModel):
    # Одно действие сотрудника (для журнала активности).
    display_id: str
    action: str
    note: Optional[str] = None
    created_at: datetime


class SharePrepareOut(BaseModel):
    # id подготовленного сообщения для Telegram.WebApp.shareMessage.
    prepared_message_id: str


# ── Импорт объявления по ссылке (AI-разбор) ──────────────────────────
class ListingImportIn(BaseModel):
    # Ссылка на объявление (Telegram, OLX, Joymee и любые другие площадки).
    url: str

    @field_validator("url")
    @classmethod
    def _strip_url(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("empty_link")
        return value


class ListingImportOut(BaseModel):
    """
    Результат предпросмотра импорта: извлечённые поля объекта (для подстановки
    в форму) + найденные ссылки на фото (прикрепятся при сохранении) +
    предупреждения (что не удалось определить).
    Ничего на этом шаге НЕ сохраняется.
    """
    name: Optional[str] = None
    type: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    rooms: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    land_area: Optional[float] = None
    area: Optional[float] = None
    condition: Optional[str] = None
    furniture_appliances: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    owner_phone: Optional[str] = None
    description: Optional[str] = None
    source_link: Optional[str] = None
    # Источник: "@канал" для Telegram-ссылок (как в массовом импорте) или домен площадки.
    source: Optional[str] = None
    # Ссылки на фотографии, найденные на странице (прямые URL картинок).
    photo_urls: List[str] = []
    # Предупреждения для пользователя (например, «фото не найдены»).
    warnings: List[str] = []


class PhotoImportUrlsIn(BaseModel):
    # Прямые ссылки на изображения для прикрепления к уже созданному объекту.
    urls: List[str] = []
