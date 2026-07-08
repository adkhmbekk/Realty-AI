"""
Доступ к данным приглашений (таблица invites).

Списки и доступ по id фильтруются по agency_id (изоляция между агентствами).
Поиск по коду — глобальный, потому что в момент вступления сотрудник ещё не
привязан ни к какому агентству (агентство определяется именно по приглашению).
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models.invite import Invite


def create(
    db: Session,
    agency_id: int,
    code: str,
    role: str,
    created_by: Optional[int],
    expires_at: datetime,
    max_uses: int = 1,
) -> Invite:
    invite = Invite(
        agency_id=agency_id,
        code=code,
        role=role,
        created_by=created_by,
        expires_at=expires_at,
        max_uses=max_uses,
    )
    db.add(invite)
    db.flush()
    return invite


def claim_use(
    db: Session, invite_id: int, telegram_id: int, now: datetime
) -> bool:
    """
    Атомарно «занять» одно использование приглашения. Одним UPDATE увеличивает
    used_count на 1 ТОЛЬКО если лимит ещё не исчерпан (used_count < max_uses) —
    так два одновременных вступления не пробьют лимит (защита от гонки).

    Возвращает True, если использование засчитано; False — если лимит исчерпан.
    Также обновляет «кто/когда вступил последним» (used_at/used_by_telegram_id).
    """
    res = db.execute(
        update(Invite)
        .where(Invite.id == invite_id, Invite.used_count < Invite.max_uses)
        .values(
            used_count=Invite.used_count + 1,
            used_at=now,
            used_by_telegram_id=telegram_id,
        )
        .execution_options(synchronize_session=False),
    )
    return res.rowcount == 1


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
