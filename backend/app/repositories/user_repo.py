"""
Доступ к данным пользователей (таблица users).
Только этот слой обращается к БД напрямую — бизнес-логика ходит сюда.
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.user import User


def get_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


def get_by_telegram_id(db: Session, telegram_id: int) -> Optional[User]:
    return db.execute(
        select(User).where(User.telegram_id == telegram_id)
    ).scalar_one_or_none()


def get_by_phone(db: Session, phone: str) -> Optional[User]:
    """Пользователь по номеру телефона (номер уникален; юзер-центричная модель)."""
    return db.execute(
        select(User).where(User.phone == phone)
    ).scalar_one_or_none()


def get_by_agency(db: Session, agency_id: int) -> List[User]:
    """Все сотрудники агентства (для управления командой)."""
    return list(
        db.execute(
            select(User)
            .where(User.agency_id == agency_id)
            .order_by(User.role, User.created_at)
        )
        .scalars()
        .all()
    )


def get_owner(db: Session, agency_id: int) -> Optional[User]:
    """Владелец агентства (главный администратор, is_owner=True). Может быть None."""
    return db.execute(
        select(User)
        .where(
            User.agency_id == agency_id,
            User.role == "agency_admin",
            User.is_owner.is_(True),
        )
        .order_by(User.created_at)
        .limit(1)
    ).scalar_one_or_none()


def get_member(db: Session, agency_id: int, user_id: int) -> Optional[User]:
    """Сотрудник по id, но только в пределах своего агентства (изоляция)."""
    return db.execute(
        select(User).where(User.id == user_id, User.agency_id == agency_id)
    ).scalar_one_or_none()


def get_by_ids(db: Session, ids) -> List[User]:
    """Несколько пользователей по их id (для отображения имён создателей)."""
    ids = list(ids)
    if not ids:
        return []
    return list(
        db.execute(select(User).where(User.id.in_(ids))).scalars().all()
    )


def create(
    db: Session,
    telegram_id: int,
    role: str,
    agency_id: Optional[int] = None,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
    is_owner: bool = False,
) -> User:
    user = User(
        telegram_id=telegram_id,
        role=role,
        agency_id=agency_id,
        username=username,
        full_name=full_name,
        is_active=True,
        is_owner=is_owner,
    )
    db.add(user)
    db.flush()  # чтобы получить сгенерированный id
    return user
