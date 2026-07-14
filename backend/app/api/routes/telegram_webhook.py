"""
Приёмник апдейтов бота входа (@realtyloginbot).
  POST /telegram/webhook — Telegram шлёт сюда message / callback_query.

Аутентификация — заголовок X-Telegram-Bot-Api-Secret-Token (задаётся при
setWebhook). Без совпадения секрета — 403 (чужой запрос). Тело — произвольный
Telegram Update (принимаем как dict). Всегда быстро отвечаем 200, чтобы Telegram
не копил повторы.
"""
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.services import tg_login_service

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Обработать апдейт бота входа (с проверкой секрета Telegram)."""
    secret = settings.telegram_webhook_secret
    got = request.headers.get("x-telegram-bot-api-secret-token")
    if not secret or got != secret:
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    try:
        update = await request.json()
    except Exception:  # noqa: BLE001
        return Response(status_code=status.HTTP_200_OK)
    if isinstance(update, dict):
        tg_login_service.handle_update(db, update)
    return {"ok": True}
