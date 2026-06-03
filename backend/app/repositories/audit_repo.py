"""
Доступ к данным журнала аудита (таблица audit_log).

add() — записать событие (без commit: пишется в той же транзакции, что и само
действие, чтобы журнал и результат были согласованы). Выборки фильтруются по
agency_id (для админа агентства) либо берутся целиком (для суперадмина).
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog


def add(
    db: Session,
    *,
    action: str,
    agency_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    actor_telegram_id: Optional[int] = None,
    actor_name: Optional[str] = None,
    target: Optional[str] = None,
    note: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        agency_id=agency_id,
        actor_user_id=actor_user_id,
        actor_telegram_id=actor_telegram_id,
        actor_name=actor_name,
        target=target,
        note=note,
    )
    db.add(entry)
    return entry


def list_for_agency(db: Session, agency_id: int, limit: int = 100) -> List[AuditLog]:
    return list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.agency_id == agency_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
