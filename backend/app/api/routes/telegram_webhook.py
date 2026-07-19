"""
Приёмник апдейтов бота входа (@realtyloginbot).
  POST /telegram/webhook — Telegram шлёт сюда message / callback_query.

Аутентификация — заголовок X-Telegram-Bot-Api-Secret-Token (задаётся при
setWebhook). Без совпадения секрета — 403 (чужой запрос). Тело — произвольный
Telegram Update (принимаем как dict). Всегда быстро отвечаем 200, чтобы Telegram
не копил повторы.
"""
import hmac
import logging

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.services import tg_login_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Обработать апдейт бота входа (с проверкой секрета Telegram)."""
    secret = settings.telegram_webhook_secret
    got = request.headers.get("x-telegram-bot-api-secret-token")
    # Постоянное по времени сравнение секрета (защита от timing-атаки, ревью L1).
    if not secret or not got or not hmac.compare_digest(got, secret):
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    try:
        update = await request.json()
    except Exception:  # noqa: BLE001
        return Response(status_code=status.HTTP_200_OK)
    if isinstance(update, dict):
        # Контракт с Telegram — всегда 200 (иначе он копит повторы), поэтому сбой
        # обработки не роняем наружу, а логируем: юзер просто нажмёт кнопку ещё раз
        # (handle_update идемпотентен по статусам кода).
        try:
            tg_login_service.handle_update(db, update)
        except Exception:  # noqa: BLE001
            logger.exception("tg login webhook: update processing failed")
    return {"ok": True}
