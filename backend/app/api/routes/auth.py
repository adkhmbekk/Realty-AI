"""
Эндпоинты входа и профиля.
Роуты не содержат бизнес-логику — они вызывают сервисы.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import AuthResponse, TelegramAuthRequest, UserProfile
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/telegram", response_model=AuthResponse)
def telegram_login(body: TelegramAuthRequest, db: Session = Depends(get_db)):
    """Принять данные входа от Telegram, проверить и выдать пропуск."""
    return auth_service.login_with_init_data(db, body.init_data)


@router.get("/me", response_model=UserProfile)
def me(current_user: User = Depends(get_current_user)):
    """Вернуть профиль текущего пользователя (по присланному пропуску)."""
    return current_user
