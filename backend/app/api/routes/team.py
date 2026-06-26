"""
Эндпоинты управления командой агентства (только администратор агентства).
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_admin
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.team import MemberAuditOut, MemberOut, MemberUpdate
from app.services import member_service

router = APIRouter(prefix="/team", tags=["team"])


@router.get("", response_model=List[MemberOut])
def list_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Список сотрудников своего агентства."""
    return member_service.list_members(db, current_user.agency_id)


# ВНИМАНИЕ: /audit объявлен ДО /{member_id}, иначе "audit" попадёт в параметр id.
@router.get("/audit", response_model=List[MemberAuditOut])
def list_audit(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Журнал действий по своему агентству (кто кого изменил/исключил и т.д.)."""
    return member_service.list_audit(db, current_user.agency_id)


@router.patch("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: int,
    body: MemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Изменить сотрудника: включить/отключить доступ и/или сменить роль."""
    return member_service.update_member(
        db, current_user.agency_id, current_user, member_id, body
    )


@router.delete("/{member_id}", status_code=204)
def remove_member(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Исключить сотрудника из агентства (только главный администратор)."""
    member_service.remove_member(db, current_user.agency_id, current_user, member_id)


@router.post("/{member_id}/revoke", response_model=MemberOut)
def revoke_member_sessions(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """«Выйти со всех устройств»: мгновенно завершить все сеансы сотрудника
    (без отключения — он сможет войти заново)."""
    return member_service.revoke_sessions(
        db, current_user.agency_id, current_user, member_id
    )


@router.post("/{member_id}/owner", response_model=MemberOut)
def transfer_ownership(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Передать роль главного администратора другому сотруднику (только главный)."""
    return member_service.transfer_ownership(
        db, current_user.agency_id, current_user, member_id
    )
