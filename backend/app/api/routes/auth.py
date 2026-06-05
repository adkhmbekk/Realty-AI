"""
Эндпоинты входа и профиля.
Роуты не содержат бизнес-логику — они вызывают сервисы.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.ratelimit import rate_limit, _client_ip
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import (
    AuthResponse,
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
    return auth_service.refresh_session(db, body.refresh_token)


@router.get("/me", response_model=UserProfile)
def me(current_user: User = Depends(get_current_user)):
    """Вернуть профиль текущего пользователя (по присланному пропуску)."""
    return current_user
