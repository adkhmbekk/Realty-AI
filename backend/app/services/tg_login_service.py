"""
Бизнес-логика входа в нативное приложение через Telegram-бота (@realtyloginbot).

Отдельный бот, изолированный от прод-бота: все вызовы Telegram Bot API идут через
settings.login_bot_token. Поток:
  1) start_login — создаём одноразовый код (pending, TTL 5 мин) и ссылку t.me;
  2) handle_update — обрабатываем апдейты бота: на «/start login_<code>» шлём
     сообщение с кнопкой «Подтвердить»; на нажатие кнопки — привязываем telegram_id
     и помечаем код confirmed;
  3) poll — приложение опрашивает код: pending / expired / confirmed(+сессия).
     Первый confirmed выдаёт JWT и делает код consumed (одноразовый).
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import AppError
from app.repositories import tg_login_repo
from app.services import auth_service

logger = logging.getLogger("uvicorn.error")

CODE_TTL_SECONDS = 300
_API = "https://api.telegram.org/bot{token}/{method}"


def _tg_api(method: str, payload: dict) -> Optional[dict]:
    """Вызов Telegram Bot API от лица БОТА ВХОДА (login_bot_token). Ошибки сети не
    роняют обработку — логируем и продолжаем (в тестах функция подменяется)."""
    if not settings.login_bot_token:
        return None
    url = _API.format(token=settings.login_bot_token, method=method)
    try:
        resp = httpx.post(url, json=payload, timeout=15.0)
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Login-bot %s не выполнен: %s", method, exc)
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime) -> datetime:
    """Привести значение из БД к timezone-aware (SQLite отдаёт naive)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def start_login(db: Session) -> dict:
    """Создать одноразовый код и ссылку t.me для входа. 503, если бот не настроен."""
    if not settings.login_bot_token or not settings.login_bot_username:
        raise AppError("telegram_login_not_configured", status.HTTP_503_SERVICE_UNAVAILABLE)
    code = secrets.token_hex(16)  # 128 бит → перебор невозможен
    expires_at = _now() + timedelta(seconds=CODE_TTL_SECONDS)
    tg_login_repo.create(db, code=code, expires_at=expires_at)
    # ВАЖНО: коммитим сразу — код должен пережить закрытие сессии этого запроса,
    # иначе webhook/poll (уже в ДРУГОЙ сессии) его не найдут (get_db не коммитит
    # на выходе → без commit строка откатывается).
    db.commit()
    deep_link = f"https://t.me/{settings.login_bot_username}?start=login_{code}"
    return {"code": code, "deep_link": deep_link, "expires_in": CODE_TTL_SECONDS}


def _send_confirm_prompt(chat_id: int, code: str) -> None:
    """Сообщение с кнопками «Подтвердить/Отмена» — только по валидному коду."""
    _tg_api("sendMessage", {
        "chat_id": chat_id,
        "text": "Кто-то входит в приложение Realty AI. Это вы?",
        "reply_markup": {"inline_keyboard": [[
            {"text": "✅ Подтвердить вход", "callback_data": f"confirm_{code}"},
            {"text": "❌ Отмена", "callback_data": f"cancel_{code}"},
        ]]},
    })


def _handle_start(db: Session, message: dict) -> None:
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is None:
        return
    parts = text.split()
    # Deep-link «/start login_<code>»: у /start ровно один аргумент.
    if len(parts) != 2 or not parts[0].startswith("/start"):
        return
    param = parts[1]
    if not param.startswith("login_"):
        return
    code = param[len("login_"):]
    row = tg_login_repo.get_by_code(db, code)
    if row is None or row.status != "pending" or _as_aware(row.expires_at) < _now():
        return
    _send_confirm_prompt(chat_id, code)


def _handle_callback(db: Session, cq: dict) -> None:
    data = cq.get("data") or ""
    cq_id = cq.get("id")
    frm = cq.get("from") or {}
    msg = cq.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    message_id = msg.get("message_id")

    def _answer(text: str) -> None:
        if cq_id:
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": text})

    def _edit(text: str) -> None:
        if chat_id is not None and message_id is not None:
            _tg_api("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text})

    if data.startswith("confirm_"):
        code = data[len("confirm_"):]
        row = tg_login_repo.get_by_code(db, code)
        if row is None or row.status != "pending" or _as_aware(row.expires_at) < _now():
            _answer("Код недействителен или истёк.")
            _edit("⌛ Ссылка входа недействительна. Запросите вход заново в приложении.")
            return
        row.status = "confirmed"
        row.telegram_id = int(frm.get("id"))
        row.tg_first_name = frm.get("first_name")
        row.tg_last_name = frm.get("last_name")
        db.commit()
        _answer("Готово")
        _edit("✅ Вход подтверждён. Вернитесь в приложение.")
    elif data.startswith("cancel_"):
        code = data[len("cancel_"):]
        row = tg_login_repo.get_by_code(db, code)
        if row is not None and row.status == "pending":
            row.status = "cancelled"
            db.commit()
        _answer("Отменено")
        _edit("❌ Вход отменён.")


def handle_update(db: Session, update: dict) -> None:
    """Единая точка входа webhook: маршрутизирует message / callback_query."""
    if "message" in update:
        _handle_start(db, update["message"])
    elif "callback_query" in update:
        _handle_callback(db, update["callback_query"])


def poll(db: Session, code: str) -> dict:
    """Опрос статуса кода приложением. Confirmed → выдаём сессию и гасим код."""
    row = tg_login_repo.get_by_code(db, code)
    # Неизвестный код → отвечаем pending (не раскрываем, существует ли он).
    if row is None:
        return {"status": "pending", "auth": None}
    if row.status == "confirmed":
        auth = auth_service.login_with_telegram_id(
            db, telegram_id=row.telegram_id,
            first_name=row.tg_first_name, last_name=row.tg_last_name,
        )
        row.status = "consumed"
        db.commit()
        return {"status": "confirmed", "auth": auth}
    if row.status in ("consumed", "cancelled"):
        return {"status": "expired", "auth": None}
    if _as_aware(row.expires_at) < _now():
        if row.status == "pending":
            row.status = "expired"
            db.commit()
        return {"status": "expired", "auth": None}
    return {"status": "pending", "auth": None}
