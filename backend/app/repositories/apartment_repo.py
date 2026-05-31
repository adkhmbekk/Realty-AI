"""
Доступ к данным объектов недвижимости (таблица apartments).

Переносит логику поиска из старого бота (search_apartments), но:
  - КАЖДЫЙ запрос обязательно фильтруется по agency_id (изоляция агентств);
  - вместо отдельной таблицы-архива используется поле status;
  - добавлены пагинация и подсчёт общего количества.
"""
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models.apartment import Apartment


def get_by_id(db: Session, agency_id: int, apartment_id: int) -> Optional[Apartment]:
    # Фильтр по agency_id обязателен — нельзя получить чужой объект по id.
    return db.execute(
        select(Apartment).where(
            Apartment.id == apartment_id, Apartment.agency_id == agency_id
        )
    ).scalar_one_or_none()


def create(db: Session, apartment: Apartment) -> Apartment:
    db.add(apartment)
    db.flush()  # чтобы получить сгенерированный id
    return apartment


def _build_conditions(
    agency_id: int,
    *,
    status: Optional[str],
    districts: Optional[Sequence[str]],
    types: Optional[Sequence[str]],
    rooms: Optional[Sequence[int]],
    floor_min: Optional[int],
    floor_max: Optional[int],
    price_min: Optional[float],
    price_max: Optional[float],
    agent_id: Optional[int],
    q: Optional[str] = None,
    rooms_min: Optional[int] = None,
    rooms_max: Optional[int] = None,
) -> list:
    # Первое и главное условие — принадлежность агентству.
    conditions = [Apartment.agency_id == agency_id]

    if status == "unsold":
        # Всё, кроме проданных (для раздела «Моя база»).
        conditions.append(Apartment.status != "sold")
    elif status:
        conditions.append(Apartment.status == status)
    if districts:
        conditions.append(Apartment.district.in_(list(districts)))
    if types:
        conditions.append(Apartment.type.in_(list(types)))
    if rooms:
        conditions.append(Apartment.rooms.in_(list(rooms)))
    if rooms_min is not None:
        conditions.append(Apartment.rooms >= rooms_min)
    if rooms_max is not None:
        conditions.append(Apartment.rooms <= rooms_max)
    if floor_min is not None:
        conditions.append(Apartment.floor >= floor_min)
    if floor_max is not None:
        conditions.append(Apartment.floor <= floor_max)
    if price_min is not None:
        conditions.append(Apartment.price >= price_min)
    if price_max is not None:
        conditions.append(Apartment.price <= price_max)
    if agent_id is not None:
        conditions.append(Apartment.agent_id == agent_id)

    # Текстовый поиск по наименованию, адресу и номеру объекта (display_id).
    if q:
        term = q.strip()
        if term:
            like = f"%{term}%"
            text_conds = [
                Apartment.name.ilike(like),
                Apartment.address.ilike(like),
                Apartment.display_id.ilike(like),
            ]
            # Если ввели цифры (например «№0001» или «1») — ищем и по номеру,
            # игнорируя ведущие нули и нецифровые символы.
            digits = "".join(ch for ch in term if ch.isdigit())
            if digits:
                text_conds.append(Apartment.display_id.ilike(f"%{digits}%"))
                stripped = digits.lstrip("0")
                if stripped and stripped != digits:
                    text_conds.append(Apartment.display_id.ilike(f"%{stripped}%"))
            conditions.append(or_(*text_conds))

    return conditions


def search(
    db: Session,
    agency_id: int,
    *,
    status: Optional[str] = "active",
    districts: Optional[Sequence[str]] = None,
    types: Optional[Sequence[str]] = None,
    rooms: Optional[Sequence[int]] = None,
    floor_min: Optional[int] = None,
    floor_max: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    agent_id: Optional[int] = None,
    q: Optional[str] = None,
    rooms_min: Optional[int] = None,
    rooms_max: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Apartment], int]:
    """
    Вернуть страницу объектов и общее количество подходящих под фильтр.
    По умолчанию показываются только активные (status='active').
    Сортировка — по дате создания (новые сверху), как в старом боте.
    """
    conditions = _build_conditions(
        agency_id,
        status=status,
        districts=districts,
        types=types,
        rooms=rooms,
        floor_min=floor_min,
        floor_max=floor_max,
        price_min=price_min,
        price_max=price_max,
        agent_id=agent_id,
        q=q,
        rooms_min=rooms_min,
        rooms_max=rooms_max,
    )

    total = db.execute(
        select(func.count()).select_from(Apartment).where(*conditions)
    ).scalar_one()

    items = list(
        db.execute(
            select(Apartment)
            .where(*conditions)
            .order_by(Apartment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return items, total
