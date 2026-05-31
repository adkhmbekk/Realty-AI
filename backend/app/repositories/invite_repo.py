"""
Доступ к данным приглашений (таблица invites).

Списки и доступ по id фильтруются по agency_id (изоляция между агентствами).
Поиск по коду — глобальный, потому что в момент вступления сотрудник ещё не
привязан ни к какому агентству (агентство определяется именно по приглашению).
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.invite import Invite


def create(
    db: Session,
    agency_id: int,
    code: str,
    role: str,
    created_by: Optional[int],
    expires_at: datetime,
) -> Invite:
    invite = Invite(
        agency_id=agency_id,
        code=code,
        role=role,
        created_by=created_by,
        expires_at=expires_at,
    )
    db.add(invite)
    db.flush()
    return invite


def get_by_code(db: Session, code: str) -> Optional[Invite]:
    # Глобальный поиск по коду (код уникален во всей таблице).
    return db.execute(
        select(Invite).where(Invite.code == code)
    ).scalar_one_or_none()


def get_by_id(db: Session, agency_id: int, invite_id: int) -> Optional[Invite]:
    return db.execute(
        select(Invite).where(Invite.id == invite_id, Invite.agency_id == agency_id)
    ).scalar_one_or_none()


def get_all(db: Session, agency_id: int) -> List[Invite]:
    return list(
        db.execute(
            select(Invite)
            .where(Invite.agency_id == agency_id)
            .order_by(Invite.created_at.desc())
        )
        .scalars()
        .all()
    )


def delete(db: Session, invite: Invite) -> None:
    db.delete(invite)
