"""
Доступ к данным пользователей (таблица users).
Только этот слой обращается к БД напрямую — бизнес-логика ходит сюда.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.user import User


def get_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


def get_by_telegram_id(db: Session, telegram_id: int) -> Optional[User]:
    return db.execute(
        select(User).where(User.telegram_id == telegram_id)
    ).scalar_one_or_none()


def create(
    db: Session,
    telegram_id: int,
    role: str,
    agency_id: Optional[int] = None,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
) -> User:
    user = User(
        telegram_id=telegram_id,
        role=role,
        agency_id=agency_id,
        username=username,
        full_name=full_name,
        is_active=True,
    )
    db.add(user)
    db.flush()  # чтобы получить сгенерированный id
    return user
