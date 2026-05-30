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

from app.core.defaults import DEFAULT_AGENT_CODE
from app.db.models.agent import Agent
from app.db.models.apartment import Apartment
from app.repositories import agent_repo, apartment_repo
from app.schemas.apartment import ApartmentCreate, ApartmentUpdate

# Допустимые статусы объекта.
STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"
STATUS_SOLD = "sold"


def _resolve_agent(db: Session, agency_id: int, agent_id: Optional[int]) -> Agent:
    """
    Определить агента, от кода которого образуется ID объекта.
    Если агент явно указан — берём его (проверив принадлежность агентству).
    Если нет — пробуем запасного агента «Другое» (код OTH), созданного по
    умолчанию при регистрации агентства.
    """
    if agent_id is not None:
        agent = agent_repo.get_by_id(db, agency_id, agent_id)
        if agent is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Указанный агент не найден в этом агентстве.",
            )
        return agent

    fallback = agent_repo.get_by_code(db, agency_id, DEFAULT_AGENT_CODE)
    if fallback is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не указан агент, и нет запасного агента. Сначала добавьте агента.",
        )
    return fallback


def _generate_display_id(db: Session, agency_id: int, agent: Agent) -> str:
    """Сгенерировать ID вида «SAR-0001» (атомарный счётчик агента)."""
    number = agent_repo.next_number(db, agency_id, agent.id)
    if number is None:
        # Теоретически недостижимо (агента мы только что проверили), но
        # перестраховываемся: лучше понятная ошибка, чем кривой ID.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось сгенерировать ID объекта.",
        )
    return f"{agent.code}-{number:04d}"


def create_apartment(
    db: Session, agency_id: int, created_by: Optional[int], payload: ApartmentCreate
) -> Apartment:
    agent = _resolve_agent(db, agency_id, payload.agent_id)
    display_id = _generate_display_id(db, agency_id, agent)

    apartment = Apartment(
        agency_id=agency_id,
        display_id=display_id,
        status=STATUS_ACTIVE,
        agent_id=agent.id,
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
    )
    apartment_repo.create(db, apartment)
    db.commit()
    db.refresh(apartment)
    return apartment


def get_apartment(db: Session, agency_id: int, apartment_id: int) -> Apartment:
    apartment = apartment_repo.get_by_id(db, agency_id, apartment_id)
    if apartment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Объект не найден."
        )
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
    limit: int = 50,
    offset: int = 0,
) -> Tuple[list, int]:
    return apartment_repo.search(
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
        limit=limit,
        offset=offset,
    )


def update_apartment(
    db: Session, agency_id: int, apartment_id: int, payload: ApartmentUpdate
) -> Apartment:
    apartment = get_apartment(db, agency_id, apartment_id)

    # exclude_unset=True → меняем только те поля, которые реально прислали.
    # Набор полей ограничен схемой ApartmentUpdate (белый список) — статус и
    # display_id поменять через этот метод нельзя.
    changes = payload.model_dump(exclude_unset=True)

    # Если меняют агента — проверяем, что он принадлежит этому агентству.
    if "agent_id" in changes and changes["agent_id"] is not None:
        agent = agent_repo.get_by_id(db, agency_id, changes["agent_id"])
        if agent is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Указанный агент не найден в этом агентстве.",
            )

    # Нормализация валюты уже сделана в схеме; пустую валюту не затираем.
    if "currency" in changes and not changes["currency"]:
        changes.pop("currency")

    for field, value in changes.items():
        setattr(apartment, field, value)

    db.commit()
    db.refresh(apartment)
    return apartment


def _set_status(
    db: Session, agency_id: int, apartment_id: int, new_status: str
) -> Apartment:
    apartment = get_apartment(db, agency_id, apartment_id)
    apartment.status = new_status
    if new_status == STATUS_ACTIVE:
        apartment.archived_at = None
    else:
        apartment.archived_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(apartment)
    return apartment


def archive_apartment(db: Session, agency_id: int, apartment_id: int) -> Apartment:
    return _set_status(db, agency_id, apartment_id, STATUS_ARCHIVED)


def restore_apartment(db: Session, agency_id: int, apartment_id: int) -> Apartment:
    return _set_status(db, agency_id, apartment_id, STATUS_ACTIVE)


def mark_sold(db: Session, agency_id: int, apartment_id: int) -> Apartment:
    return _set_status(db, agency_id, apartment_id, STATUS_SOLD)


def delete_apartment(db: Session, agency_id: int, apartment_id: int) -> None:
    apartment = get_apartment(db, agency_id, apartment_id)
    db.delete(apartment)
    db.commit()
