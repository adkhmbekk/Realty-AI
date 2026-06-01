"""
Доступ к данным объектов недвижимости (таблица apartments).

Переносит логику поиска из старого бота (search_apartments), но:
  - КАЖДЫЙ запрос обязательно фильтруется по agency_id (изоляция агентств);
  - вместо отдельной таблицы-архива используется поле status;
  - добавлены пагинация и подсчёт общего количества.
"""
from typing import List, Optional, Sequence, Tuple

from datetime import datetime, timezone

from sqlalchemy import and_, case, func, or_, select
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
    created_by: Optional[int] = None,
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
    if created_by is not None:
        conditions.append(Apartment.created_by == created_by)

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
    created_by: Optional[int] = None,
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
        created_by=created_by,
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


def count_by_status(db: Session, agency_id: int) -> dict:
    """Вернуть количество объектов агентства по каждому статусу."""
    rows = db.execute(
        select(Apartment.status, func.count())
        .where(Apartment.agency_id == agency_id)
        .group_by(Apartment.status)
    ).all()
    return {row[0]: row[1] for row in rows}


def _month_start_utc() -> datetime:
    """Начало текущего месяца в UTC (для подсчётов «за этот месяц»)."""
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def count_created_since(db: Session, agency_id: int, since: datetime) -> int:
    """Сколько объектов добавлено с момента since."""
    return db.execute(
        select(func.count())
        .select_from(Apartment)
        .where(Apartment.agency_id == agency_id, Apartment.created_at >= since)
    ).scalar_one()


def count_sold_since(db: Session, agency_id: int, since: datetime) -> int:
    """Сколько объектов продано (status='sold') с момента since (по дате снятия)."""
    return db.execute(
        select(func.count())
        .select_from(Apartment)
        .where(
            Apartment.agency_id == agency_id,
            Apartment.status == "sold",
            Apartment.archived_at >= since,
        )
    ).scalar_one()


def stats_by_creator(db: Session, agency_id: int) -> List[Tuple[Optional[int], int, int]]:
    """
    Активность по сотрудникам: для каждого создателя — (created_by, всего, продано).
    """
    sold_expr = func.sum(case((Apartment.status == "sold", 1), else_=0))
    rows = db.execute(
        select(Apartment.created_by, func.count(), sold_expr)
        .where(Apartment.agency_id == agency_id)
        .group_by(Apartment.created_by)
    ).all()
    return [(row[0], int(row[1]), int(row[2] or 0)) for row in rows]


def timeseries_counts(db: Session, agency_id: int, since: datetime, granularity: str):
    """
    Подсчитать «добавлено» и «продано» по периодам (для графиков).
    granularity: 'day' или 'month'. Возвращает два словаря {дата_корзины: число}.
    """
    created_bucket = func.date_trunc(granularity, Apartment.created_at)
    created_rows = db.execute(
        select(created_bucket, func.count())
        .where(Apartment.agency_id == agency_id, Apartment.created_at >= since)
        .group_by(created_bucket)
    ).all()

    sold_bucket = func.date_trunc(granularity, Apartment.archived_at)
    sold_rows = db.execute(
        select(sold_bucket, func.count())
        .where(
            Apartment.agency_id == agency_id,
            Apartment.status == "sold",
            Apartment.archived_at >= since,
        )
        .group_by(sold_bucket)
    ).all()

    def _keyize(rows) -> dict:
        out = {}
        for bucket, count in rows:
            if bucket is None:
                continue
            key = bucket.date() if hasattr(bucket, "date") else bucket
            out[key] = int(count)
        return out

    return _keyize(created_rows), _keyize(sold_rows)


def find_similar(
    db: Session,
    agency_id: int,
    *,
    district: Optional[str] = None,
    rooms: Optional[int] = None,
    type_: Optional[str] = None,
    price: Optional[float] = None,
    address: Optional[str] = None,
    exclude_id: Optional[int] = None,
    limit: int = 5,
) -> List[Apartment]:
    """
    Найти возможные дубли объекта среди активных/задаточных объектов агентства.

    Совпадением считается:
      A) одинаковый адрес (без учёта регистра), либо
      B) одинаковые район + кол-во комнат (+ тип, если задан) и цена в пределах
         ±10 %, если цены указаны у обоих.
    """
    base = [
        Apartment.agency_id == agency_id,
        Apartment.status.in_(["active", "deposit"]),
    ]
    if exclude_id is not None:
        base.append(Apartment.id != exclude_id)

    match_clauses = []

    addr = (address or "").strip()
    if addr:
        match_clauses.append(func.lower(Apartment.address) == addr.lower())

    # Характеристики имеют смысл только если есть хотя бы район и кол-во комнат.
    if district and rooms is not None:
        char_conds = [Apartment.district == district, Apartment.rooms == rooms]
        if type_:
            char_conds.append(Apartment.type == type_)
        if price is not None and price > 0:
            char_conds.append(Apartment.price >= price * 0.9)
            char_conds.append(Apartment.price <= price * 1.1)
        match_clauses.append(and_(*char_conds))

    if not match_clauses:
        return []

    conditions = base + [or_(*match_clauses)]
    return list(
        db.execute(
            select(Apartment)
            .where(*conditions)
            .order_by(Apartment.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
