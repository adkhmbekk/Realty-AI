"""
Эндпоинты входа и профиля.
Роуты не содержат бизнес-логику — они вызывают сервисы.
"""
from typing import List

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.ratelimit import rate_limit, _client_ip
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import (
    AuthResponse,
    MembershipOut,
    ProfileUpdate,
    RefreshRequest,
    TelegramAuthRequest,
    UserProfile,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/telegram",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit(15, 60, "auth_telegram"))],
)
def telegram_login(body: TelegramAuthRequest, request: Request, db: Session = Depends(get_db)):
    """Принять данные входа от Telegram, проверить и выдать пропуск."""
    return auth_service.login_with_init_data(db, body.init_data, ip=_client_ip(request))


@router.post(
    "/refresh",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit(30, 60, "auth_refresh"))],
)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    """Обновить сессию по refresh-пропуску (без повторной проверки initData)."""
    return auth_service.refresh_session(
        db, body.refresh_token, act_as_agency_id=body.act_as_agency_id
    )


@router.get("/me", response_model=UserProfile)
def me(current_user: User = Depends(get_current_user)):
    """Вернуть профиль текущего пользователя (по присланному пропуску)."""
    return current_user


@router.patch("/me", response_model=UserProfile)
def update_me(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Обновить личный профиль (имя/фамилия/язык)."""
    return auth_service.update_profile(
        db,
        current_user,
        first_name=body.first_name,
        last_name=body.last_name,
        language=body.language,
    )


@router.get("/memberships", response_model=List[MembershipOut])
def my_memberships(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Агентства, в которых состоит пользователь (для переключателя «мои агентства»)."""
    return auth_service.list_my_memberships(db, current_user)


@router.post(
    "/heartbeat",
    status_code=204,
    dependencies=[Depends(rate_limit(60, 60, "auth_heartbeat"))],
)
def heartbeat(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Отметить присутствие пользователя «в сети» (периодический пинг из приложения)."""
    auth_service.touch_last_seen(db, current_user.id)
