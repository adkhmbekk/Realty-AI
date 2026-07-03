"""
Схемы витрины общей базы (MLS) для владельца платформы.

Один элемент = объект из общей базы + к какому агентству он принадлежит.
Контакты собственника в самом объекте уже скрыты сервисом (см. mls_service).
"""
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.apartment import ApartmentOut


class MlsPoolItemOut(BaseModel):
    # Какому агентству принадлежит объект (для контроля наполнения общей базы).
    agency_id: int
    agency_name: Optional[str] = None
    # Контактный номер агентства-владельца (agency.contact_phone): по нему другое
    # агентство может связаться с риелтором, выложившим объект в общую базу.
    # Это НЕ номер собственника (он скрыт) — это публичный контакт агентства.
    agency_phone: Optional[str] = None
    # Сам объект (с уже скрытыми телефоном/адресом/автором — как видят агентства).
    apartment: ApartmentOut


class MlsPoolOut(BaseModel):
    # Страница витрины: объекты + общее число подходящих под фильтр.
    items: List[MlsPoolItemOut]
    total: int
    limit: int
    offset: int
