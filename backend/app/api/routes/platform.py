"""
Эндпоинты уровня платформы (только суперадмин).

Передача прав владельца платформы другому человеку.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_superadmin
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import UserProfile
from app.schemas.platform import SuperadminTransfer
from app.services import platform_service

router = APIRouter(prefix="/platform", tags=["platform"])


@router.post("/transfer-ownership", response_model=UserProfile)
def transfer_ownership(
    body: SuperadminTransfer,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """
    Передать роль владельца платформы (суперадмина) другому человеку.
    После передачи текущий владелец теряет доступ.
    """
    return platform_service.transfer_superadmin(
        db, current_user, body.new_telegram_id, body.new_username
    )
