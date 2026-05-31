"""
Бизнес-логика объектов недвижимости (ядро ценности продукта).

Здесь живут правила домена:
  - генерация человекочитаемого ID (display_id) из кода агента и счётчика;
  - создание/редактирование объекта (редактирование — только по белому списку
    полей, см. ApartmentUpdate);
  - перевод в архив / восстановление / пометка «продан»;
  - поиск с фильтрами.

Изоляция по агентству обеспечивается тем, что все вызовы репозитория получают
agency_id текущего пользователя (а сам agency_id берётся из сессии, не с фронта).
"""
from datetime import datetime, timezone
from typing import Optional, Sequence, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.defaults import DEFAULT_AGENT_CODE, DEFAULT_AGENT_NAME
from app.db.models.apartment import Apartment
from app.repositories import agent_repo, apartment_repo, user_repo
from app.schemas.apartment import ApartmentCreate, ApartmentUpdate

# Допустимые статусы объекта.
STATUS_ACTIVE = "active"
STATUS_DEPOSIT = "deposit"     # задаток внесён — объект «придержан»
STATUS_SOLD = "sold"
STATUS_ARCHIVED = "archived"
VALID_STATUSES = (STATUS_ACTIVE, STATUS_DEPOSIT, STATUS_SOLD, STATUS_ARCHIVED)
# Статусы, при которых объект считается снятым с продажи (фиксируем дату).
_CLOSED_STATUSES = (STATUS_SOLD, STATUS_ARCHIVED)


def _next_display_id(db: Session, agency_id: int) -> str:
    """
    Сгенерировать сквозной номер объекта агентства, например «0001».

    Агент пользователем НЕ выбирается — объект всегда привязывается к тому,
    кто его создал (поле created_by). Номер берётся из атомарного служебного
    счётчика агентства (используем для этого служебную запись-счётчик).
    """
    counter = agent_repo.get_by_code(db, agency_id, DEFAULT_AGENT_CODE)
    if counter is None:
        # Подстраховка для агентств без служебного счётчика.
        counter = agent_repo.create(
            db, agency_id, name=DEFAULT_AGENT_NAME, code=DEFAULT_AGENT_CODE
        )
    number = agent_repo.next_number(db, agency_id, counter.id)
    if number is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось сгенерировать номер объекта.",
        )
    return f"{number:04d}"


def _display_name(u) -> Optional[str]:
    """Человекочитаемое имя сотрудника для отметки «кто добавил»."""
    if u is None:
        return None
    if u.full_name:
        return u.full_name
    if u.username:
        return "@" + u.username
    return f"ID {u.telegram_id}"


def _attach_creators(db: Session, apartments) -> None:
    """Проставить объектам имя создателя (created_by_name) для отображения."""
    ids = {a.created_by for a in apartments if a.created_by is not None}
    names = {}
    if ids:
        for u in user_repo.get_by_ids(db, ids):
            names[u.id] = _display_name(u)
    for a in apartments:
        a.created_by_name = names.get(a.created_by)


def create_apartment(
    db: Session, agency_id: int, created_by: Optional[int], payload: ApartmentCreate
) -> Apartment:
    display_id = _next_display_id(db, agency_id)

    new_status = payload.status or STATUS_ACTIVE
    apartment = Apartment(
        agency_id=agency_id,
        display_id=display_id,
        status=new_status,
        agent_id=None,
        created_by=created_by,
        name=payload.name,
        phone=payload.phone,
        district=payload.district,
        address=payload.address,
        type=payload.type,
        rooms=payload.rooms,
        floor=payload.floor,
        total_floors=payload.total_floors,
        area=payload.area,
        condition=payload.condition,
        furniture=payload.furniture,
        appliances=payload.appliances,
        price=payload.price,
        currency=payload.currency or "USD",
        description=payload.description,
        archived_at=datetime.now(timezone.utc) if new_status in _CLOSED_STATUSES else None,
    )
    apartment_repo.create(db, apartment)
    db.commit()
    db.refresh(apartment)
    _attach_creators(db, [apartment])
    return apartment


def get_apartment(db: Session, agency_id: int, apartment_id: int) -> Apartment:
    apartment = apartment_repo.get_by_id(db, agency_id, apartment_id)
    if apartment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Объект не найден."
        )
    _attach_creators(db, [apartment])
    return apartment


def search_apartments(
    db: Session,
    agency_id: int,
    *,
    status_filter: Optional[str] = STATUS_ACTIVE,
    districts: Optional[Sequence[str]] = None,
    types: Optional[Sequence[str]] = None,
    rooms: Optional[Sequence[int]] = None,
    floor_min: Optional[int] = None,
    floor_max: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    agent_id: Optional[int] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[list, int]:
    items, total = apartment_repo.search(
        db,
        agency_id,
        status=status_filter,
        districts=districts,
        types=types,
        rooms=rooms,
        floor_min=floor_min,
        floor_max=floor_max,
        price_min=price_min,
        price_max=price_max,
        agent_id=agent_id,
        q=q,
        limit=limit,
        offset=offset,
    )
    _attach_creators(db, items)
    return items, total


def update_apartment(
    db: Session, agency_id: int, apartment_id: int, payload: ApartmentUpdate
) -> Apartment:
    apartment = get_apartment(db, agency_id, apartment_id)

    # exclude_unset=True → меняем только те поля, которые реально прислали.
    # Набор полей ограничен схемой ApartmentUpdate (белый список) — статус и
    # display_id поменять через этот метод нельзя.
    changes = payload.model_dump(exclude_unset=True)

    # Агент объекта не редактируется: объект привязан к своему создателю.
    changes.pop("agent_id", None)

    # Нормализация валюты уже сделана в схеме; пустую валюту не затираем.
    if "currency" in changes and not changes["currency"]:
        changes.pop("currency")

    for field, value in changes.items():
        setattr(apartment, field, value)

    db.commit()
    db.refresh(apartment)
    _attach_creators(db, [apartment])
    return apartment


def set_status(
    db: Session, agency_id: int, apartment_id: int, new_status: str
) -> Apartment:
    """Сменить статус объекта (active / deposit / sold / archived)."""
    if new_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недопустимый статус объекта.",
        )
    apartment = get_apartment(db, agency_id, apartment_id)
    apartment.status = new_status
    # Фиксируем дату снятия с продажи для архива/продажи; иначе сбрасываем.
    apartment.archived_at = (
        datetime.now(timezone.utc) if new_status in _CLOSED_STATUSES else None
    )
    db.commit()
    db.refresh(apartment)
    return apartment


def delete_apartment(db: Session, agency_id: int, apartment_id: int) -> None:
    apartment = get_apartment(db, agency_id, apartment_id)
    db.delete(apartment)
    db.commit()
