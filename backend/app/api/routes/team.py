"""
Эндпоинты управления командой агентства (только администратор агентства).
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_admin
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.team import MemberOut, MemberUpdate
from app.services import member_service

router = APIRouter(prefix="/team", tags=["team"])


@router.get("", response_model=List[MemberOut])
def list_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Список сотрудников своего агентства."""
    return member_service.list_members(db, current_user.agency_id)


@router.patch("/{member_id}", response_model=MemberOut)
def update_member(
    member_id: int,
    body: MemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Изменить сотрудника (пока — включить/отключить доступ)."""
    return member_service.update_member(
        db, current_user.agency_id, current_user, member_id, body
    )
