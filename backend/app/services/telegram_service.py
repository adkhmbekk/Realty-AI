"""
Отправка сообщений и фотографий через Telegram Bot API.

Используется для:
  - «поделиться объектом с фото»: бот присылает сотруднику альбом фотографий с
    подписью, который тот пересылает клиенту;
  - уведомлений: бот сообщает руководителям агентства / суперадмину.

HTTP-вызовы выполняются через httpx (с таймаутами). Любая сетевая ошибка не
должна ломать основную операцию — функции возвращают True/False и пишут
предупреждение в лог, но не выбрасывают исключения. Публичные имена и сигнатуры
функций сохранены (на них опираются вызывающие места и тесты).
"""
import json
import logging
import threading
from typing import Optional, Sequence, Tuple

import httpx

from app.config import settings

logger = logging.getLogger("uvicorn.error")

_API = "https://api.telegram.org/bot{token}/{method}"
# Лимиты Telegram: до 10 медиа в альбоме, подпись до ~1024 символов.
_MAX_MEDIA = 10
_MAX_CAPTION = 1024
# Таймаут для загрузки альбома (медиа крупнее текстовых запросов).
_MEDIA_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def is_configured() -> bool:
    """True, если задан токен бота (иначе отправлять некуда)."""
    return bool(settings.bot_token)


def _post_json(method: str, payload: dict, timeout: float = 15.0) -> Optional[dict]:
    if not settings.bot_token:
        return None
    url = _API.format(token=settings.bot_token, method=method)
    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram %s не выполнен: %s", method, exc)
        return None


def send_message(chat_id: int, text: str) -> bool:
    """Отправить текстовое сообщение пользователю/в чат."""
    res = _post_json(
        "sendMessage",
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
    )
    return bool(res and res.get("ok"))


def _ext_for(ctype: str) -> str:
    c = (ctype or "").lower()
    if "png" in c:
        return "png"
    if "webp" in c:
        return "webp"
    return "jpg"


def send_media_group(
    chat_id: int, photos: Sequence[Tuple[bytes, str]], caption: Optional[str] = None
) -> bool:
    """
    Отправить альбом фотографий (до 10) с подписью на первом фото.
    photos: список (байты, content_type). Файлы загружаются напрямую (не по URL).
    Сборку multipart делает httpx (files=) — без ручного формирования тела.
    """
    if not settings.bot_token or not photos:
        return False
    items = list(photos)[:_MAX_MEDIA]
    media = []
    files = {}
    for i, (content, ctype) in enumerate(items):
        if not content:
            continue
        name = f"photo{i}"
        entry = {"type": "photo", "media": f"attach://{name}"}
        if i == 0 and caption:
            entry["caption"] = caption[:_MAX_CAPTION]
        media.append(entry)
        files[name] = (f"{name}.{_ext_for(ctype)}", content, ctype or "image/jpeg")
    if not media:
        return False
    url = _API.format(token=settings.bot_token, method="sendMediaGroup")
    try:
        resp = httpx.post(
            url,
            data={"chat_id": str(chat_id), "media": json.dumps(media)},
            files=files,
            timeout=_MEDIA_TIMEOUT,
        )
        res = resp.json()
        return bool(res and res.get("ok"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram sendMediaGroup не выполнен: %s", exc)
        return False


def notify_async(chat_ids: Sequence[int], text: str) -> None:
    """
    Разослать текстовое уведомление списку получателей в фоне (не блокируя
    основной запрос). Ошибки игнорируются — уведомление не критично.
    """
    targets = [c for c in dict.fromkeys(chat_ids) if c]
    if not targets or not settings.bot_token:
        return

    def _run():
        for chat_id in targets:
            try:
                send_message(chat_id, text)
            except Exception as exc:  # noqa: BLE001
                # Уведомление некритично, но сбой должен быть виден в логах.
                logger.warning("Уведомление в чат %s не отправлено: %s", chat_id, exc)

    threading.Thread(target=_run, daemon=True).start()


def save_prepared_inline_message(user_id: int, result: dict) -> Optional[str]:
    """
    Подготовить сообщение, которое пользователь сможет отправить в выбранный им
    чат (метод Bot API savePreparedInlineMessage). Возвращает id подготовленного
    сообщения либо None при ошибке.
    """
    res = _post_json(
        "savePreparedInlineMessage",
        {
            "user_id": user_id,
            "result": result,
            "allow_user_chats": True,
            "allow_group_chats": True,
            "allow_channel_chats": True,
            "allow_bot_chats": False,
        },
    )
    if res and res.get("ok"):
        return (res.get("result") or {}).get("id")
    return None
