"""
Роуты входа через Telegram-бота (нативное приложение):
  POST /auth/telegram/start — получить одноразовый код и ссылку t.me;
  POST /auth/telegram/poll  — опросить статус (pending/expired/confirmed+сессия).

Логика — в tg_login_service. Оба роута публичные (до входа), поэтому под rate-limit.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.ratelimit import rate_limit
from app.db.session import get_db
from app.schemas.telegram_login import (
    TelegramPollRequest,
    TelegramPollResponse,
    TelegramStartResponse,
)
from app.services import tg_login_service

router = APIRouter(prefix="/auth/telegram", tags=["auth"])


@router.post(
    "/start",
    response_model=TelegramStartResponse,
    dependencies=[Depends(rate_limit(20, 60, "tg_login_start"))],
)
def start(db: Session = Depends(get_db)):
    """Создать одноразовый код и ссылку на бота входа."""
    return tg_login_service.start_login(db)


@router.post(
    "/poll",
    response_model=TelegramPollResponse,
    dependencies=[Depends(rate_limit(120, 60, "tg_login_poll"))],
)
def poll(body: TelegramPollRequest, db: Session = Depends(get_db)):
    """Опросить статус кода. Confirmed → выдаём сессию (одноразово)."""
    return tg_login_service.poll(db, body.code)
