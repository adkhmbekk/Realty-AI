"""
Доступ к данным справочников (таблица dictionaries).
Все функции фильтруют по agency_id — изоляция между агентствами.
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.dictionary import Dictionary


def get_all(
    db: Session,
    agency_id: int,
    category: Optional[str] = None,
    include_inactive: bool = False,
) -> List[Dictionary]:
    stmt = select(Dictionary).where(Dictionary.agency_id == agency_id)
    if category:
        stmt = stmt.where(Dictionary.category == category)
    if not include_inactive:
        stmt = stmt.where(Dictionary.is_active.is_(True))
    stmt = stmt.order_by(Dictionary.category, Dictionary.sort_order, Dictionary.value)
    return list(db.execute(stmt).scalars().all())


def get_by_id(db: Session, agency_id: int, dict_id: int) -> Optional[Dictionary]:
    return db.execute(
        select(Dictionary).where(
            Dictionary.id == dict_id, Dictionary.agency_id == agency_id
        )
    ).scalar_one_or_none()


def get_one(
    db: Session, agency_id: int, category: str, value: str
) -> Optional[Dictionary]:
    return db.execute(
        select(Dictionary).where(
            Dictionary.agency_id == agency_id,
            Dictionary.category == category,
            Dictionary.value == value,
        )
    ).scalar_one_or_none()


def create(
    db: Session, agency_id: int, category: str, value: str, sort_order: int = 0
) -> Dictionary:
    item = Dictionary(
        agency_id=agency_id,
        category=category,
        value=value,
        sort_order=sort_order,
        is_active=True,
    )
    db.add(item)
    db.flush()
    return item


def delete(db: Session, item: Dictionary) -> None:
    db.delete(item)
