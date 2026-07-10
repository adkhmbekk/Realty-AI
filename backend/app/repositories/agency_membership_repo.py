"""
Репозиторий членства пользователя в агентствах (основа многоролевости, 2026-07).

Один человек может состоять в нескольких агентствах с разными ролями. Таблица
agency_memberships — источник правды. Существующие User.agency_id/role/is_owner
остаются «домашним» членством (совместимость).
"""
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.agency import Agency
from app.db.models.agency_membership import AgencyMembership


def get(db: Session, user_id: int, agency_id: int) -> Optional[AgencyMembership]:
    """Членство пользователя в конкретном агентстве (или None)."""
    return db.execute(
        select(AgencyMembership).where(
            AgencyMembership.user_id == user_id,
            AgencyMembership.agency_id == agency_id,
        )
    ).scalar_one_or_none()


def list_for_user(db: Session, user_id: int) -> List[Tuple[AgencyMembership, Agency]]:
    """Все членства пользователя вместе с агентством (для списка/переключателя)."""
    rows = db.execute(
        select(AgencyMembership, Agency)
        .join(Agency, AgencyMembership.agency_id == Agency.id)
        .where(AgencyMembership.user_id == user_id)
        .order_by(AgencyMembership.created_at, AgencyMembership.id)
    ).all()
    return [(m, a) for m, a in rows]


def counts_for_users(db: Session, user_ids: List[int]) -> Dict[int, int]:
    """Сколько активных членств у каждого из перечисленных пользователей —
    одним запросом (без N+1). Для витрины «юзеры» у владельца платформы."""
    if not user_ids:
        return {}
    rows = db.execute(
        select(AgencyMembership.user_id, func.count())
        .where(AgencyMembership.user_id.in_(user_ids))
        .group_by(AgencyMembership.user_id)
    ).all()
    return {uid: cnt for uid, cnt in rows}


def create(
    db: Session,
    *,
    user_id: int,
    agency_id: int,
    role: str,
    is_owner: bool = False,
    is_active: bool = True,
) -> AgencyMembership:
    m = AgencyMembership(
        user_id=user_id,
        agency_id=agency_id,
        role=role,
        is_owner=is_owner,
        is_active=is_active,
    )
    db.add(m)
    db.flush()
    return m


def get_or_create(
    db: Session,
    *,
    user_id: int,
    agency_id: int,
    role: str,
    is_owner: bool = False,
    is_active: bool = True,
) -> AgencyMembership:
    """Идемпотентно: вернуть существующее членство или создать новое."""
    existing = get(db, user_id, agency_id)
    if existing is not None:
        return existing
    return create(
        db,
        user_id=user_id,
        agency_id=agency_id,
        role=role,
        is_owner=is_owner,
        is_active=is_active,
    )
