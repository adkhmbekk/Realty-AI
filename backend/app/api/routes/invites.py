"""
Эндпоинты приглашений сотрудников (Этап 2).

Создание / список / отзыв — администратор агентства. Главный админ (владелец)
может приглашать и админов, и агентов; обычный админ — только агентов
(ограничение проверяется в invite_service по флагу is_owner).
Вступление по коду (redeem) — публичный эндпоинт: личность подтверждается
не пропуском (его у нового сотрудника ещё нет), а подписью Telegram (initData).
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_admin
from app.core.ratelimit import rate_limit
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import AuthResponse
from app.schemas.invite import InviteCreate, InviteOut, InviteRedeem
from app.services import invite_service

router = APIRouter(prefix="/invites", tags=["invites"])


@router.post("", response_model=InviteOut, status_code=201)
def create_invite(
    body: InviteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Создать приглашение сотрудника (роль + срок). Вернёт код и ссылку.

    Главный админ может приглашать админов и агентов; обычный админ — только агентов.
    """
    return invite_service.create_invite(
        db,
        current_user.agency_id,
        created_by=current_user.id,
        payload=body,
        is_owner=bool(current_user.is_owner),
    )


@router.get("", response_model=List[InviteOut])
def list_invites(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Список приглашений своего агентства (с их статусом)."""
    return invite_service.list_invites(db, current_user.agency_id)


@router.delete("/{invite_id}", status_code=204)
def revoke_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Отозвать (удалить) приглашение."""
    invite_service.revoke_invite(db, current_user.agency_id, invite_id)


@router.post(
    "/redeem",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit(15, 60, "invite_redeem"))],
)
def redeem_invite(body: InviteRedeem, db: Session = Depends(get_db)):
    """
    Вступить в агентство по коду приглашения.
    Публичный эндпоинт: проверяет подпись Telegram (initData) и код,
    привязывает пользователя к агентству и выдаёт пропуск.
    """
    return invite_service.redeem_invite(db, body.init_data, body.code)
