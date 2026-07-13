"""
Схемы витрины «юзеры прошки» для владельца платформы (Фаза 5, 2026-07).

Приватность (решение владельца): суперадмин видит юзеров, их агентства/роли и их
ОБЪЕКТЫ (листинги). Клиентская база (CRM) сюда НЕ входит — она остаётся приватной
внутри агентства.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.apartment import ApartmentOut


class PlatformUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool = True
    last_seen_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # Когда удалён (в архиве). NULL — активный.
    archived_at: Optional[datetime] = None
    # Во скольких агентствах состоит (для списка).
    agencies_count: int = 0
    # Присутствие «прямо сейчас»: online / recent («был только что») / offline.
    presence: str = "offline"
    # Вовлечённость «в целом»: active / quiet / asleep / never.
    engagement: str = "never"


class PlatformUserStats(BaseModel):
    # Сводка по тирам вовлечённости — по ВСЕМ активным юзерам (не по странице).
    active: int = 0
    quiet: int = 0
    asleep: int = 0
    never: int = 0


class PlatformUserList(BaseModel):
    items: List[PlatformUserOut]
    total: int
    limit: int
    offset: int
    # Плашка-сводка сверху списка. Только для активной вкладки (в архиве — None).
    stats: Optional[PlatformUserStats] = None


class PlatformUserAgency(BaseModel):
    # Одно агентство юзера + его роль в нём (для карточки юзера).
    agency_id: int
    agency_name: str
    role: str
    is_owner: bool = False
    # Заморожено вместе с архивацией владельца.
    is_frozen: bool = False


class ArchiveUserRequest(BaseModel):
    # Заморозить ли агентства, где юзер — владелец (агенты потеряют доступ).
    freeze_agencies: bool = False


class RestoreUserRequest(BaseModel):
    # Активный юзер, которому передать владельческие агентства архивного.
    target_user_id: int


class PlatformUserDetail(BaseModel):
    # Карточка юзера: профиль + агентства + ЕГО объекты (без клиентов).
    user: PlatformUserOut
    agencies: List[PlatformUserAgency]
    objects: List[ApartmentOut]
    objects_total: int
