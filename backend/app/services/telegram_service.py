"""
Отправка сообщений и фотографий через Telegram Bot API.

Используется для:
  - «поделиться объектом с фото»: бот присылает сотруднику альбом фотографий с
    подписью, который тот пересылает клиенту;
  - уведомлений: бот сообщает руководителям агентства о новом объекте.

Всё построено на стандартной библиотеке (urllib), без внешних зависимостей.
Любая сетевая ошибка не должна ломать основную операцию — поэтому функции
возвращают True/False и пишут предупреждение в лог, но не выбрасывают исключения.
"""
import io
import json
import logging
import threading
import urllib.request
import uuid
from typing import List, Optional, Sequence, Tuple

from app.config import settings

logger = logging.getLogger("uvicorn.error")

_API = "https://api.telegram.org/bot{token}/{method}"
# Лимиты Telegram: до 10 медиа в альбоме, подпись до ~1024 символов.
_MAX_MEDIA = 10
_MAX_CAPTION = 1024


def is_configured() -> bool:
    """True, если задан токен бота (иначе отправлять некуда)."""
    return bool(settings.bot_token)


def _post_json(method: str, payload: dict, timeout: int = 15) -> Optional[dict]:
    if not settings.bot_token:
        return None
    url = _API.format(token=settings.bot_token, method=method)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
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


def _build_multipart(fields: dict, files: List[Tuple[str, str, str, bytes]]) -> Tuple[bytes, str]:
    """
    Собрать тело multipart/form-data вручную (stdlib не умеет это из коробки).
    files: список (имя_поля, имя_файла, content_type, байты).
    Возвращает (тело, значение заголовка Content-Type).
    """
    boundary = "----RealtyAI" + uuid.uuid4().hex
    bnd = boundary.encode("utf-8")
    crlf = b"\r\n"
    buf = io.BytesIO()
    for name, value in fields.items():
        buf.write(b"--" + bnd + crlf)
        buf.write(f'Content-Disposition: form-data; name="{name}"'.encode("utf-8") + crlf + crlf)
        buf.write(str(value).encode("utf-8") + crlf)
    for name, filename, ctype, content in files:
        buf.write(b"--" + bnd + crlf)
        buf.write(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode("utf-8")
            + crlf
        )
        buf.write(f"Content-Type: {ctype}".encode("utf-8") + crlf + crlf)
        buf.write(content + crlf)
    buf.write(b"--" + bnd + b"--" + crlf)
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


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
    photos: список (байты, content_type). Файлы загружаются напрямую (не по URL),
    поэтому работает независимо от внешней доступности нашего сервера.
    """
    if not settings.bot_token or not photos:
        return False
    items = list(photos)[:_MAX_MEDIA]
    media = []
    files: List[Tuple[str, str, str, bytes]] = []
    for i, (content, ctype) in enumerate(items):
        if not content:
            continue
        name = f"photo{i}"
        entry = {"type": "photo", "media": f"attach://{name}"}
        if i == 0 and caption:
            entry["caption"] = caption[:_MAX_CAPTION]
        media.append(entry)
        files.append((name, f"{name}.{_ext_for(ctype)}", ctype or "image/jpeg", content))
    if not media:
        return False
    body, content_type = _build_multipart(
        {"chat_id": str(chat_id), "media": json.dumps(media)}, files
    )
    url = _API.format(token=settings.bot_token, method="sendMediaGroup")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            res = json.loads(resp.read().decode("utf-8"))
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
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=_run, daemon=True).start()


def save_prepared_inline_message(user_id: int, result: dict) -> Optional[str]:
    """
    Подготовить сообщение, которое пользователь сможет отправить в выбранный им
    чат (метод Bot API savePreparedInlineMessage). Возвращает id подготовленного
    сообщения (его затем передаёт фронтенд в Telegram.WebApp.shareMessage) либо
    None при ошибке. Это и есть «отправить напрямую, кому выберу».
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
