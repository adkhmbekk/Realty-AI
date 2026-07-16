"""
Отправка SMS через Eskiz.uz (notify.eskiz.uz) — для входа по номеру телефона.

Пока учётка Eskiz не задана в .env (ESKIZ_EMAIL/ESKIZ_PASSWORD), is_configured()
= False и вход по SMS отвечает 503 sms_not_configured — кнопка в приложении
честно говорит «пока недоступно». Как только ключи появятся — всё оживает без
правок кода.

Токен Eskiz живёт ~30 дней: держим его в памяти и перелогиниваемся на 401.
Любая сетевая ошибка не роняет запрос — возвращаем False, решает вызывающий.
"""
import logging
import threading
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://notify.eskiz.uz/api"
_TIMEOUT = httpx.Timeout(15.0, connect=10.0)

_token_lock = threading.Lock()
_token: Optional[str] = None


def is_configured() -> bool:
    return bool(settings.eskiz_email and settings.eskiz_password)


def _login() -> Optional[str]:
    """Получить bearer-токен Eskiz (email+password). None — если не вышло."""
    try:
        resp = httpx.post(
            f"{_BASE}/auth/login",
            data={"email": settings.eskiz_email, "password": settings.eskiz_password},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.error("eskiz login failed: HTTP %s", resp.status_code)
            return None
        return (resp.json().get("data") or {}).get("token")
    except Exception:  # noqa: BLE001
        logger.exception("eskiz login failed")
        return None


def _get_token(force: bool = False) -> Optional[str]:
    global _token
    with _token_lock:
        if _token is None or force:
            _token = _login()
        return _token


def send_sms(phone: str, text: str) -> bool:
    """Отправить SMS. phone — нормализованный '+998…' (Eskiz ждёт без '+')."""
    if not is_configured():
        return False
    token = _get_token()
    if not token:
        return False
    payload = {
        "mobile_phone": phone.lstrip("+"),
        "message": text,
        "from": settings.eskiz_from,
    }
    try:
        resp = httpx.post(
            f"{_BASE}/message/sms/send",
            data=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
        )
        # Токен истёк (~30 дней) — перелогиниваемся один раз и повторяем.
        if resp.status_code == 401:
            token = _get_token(force=True)
            if not token:
                return False
            resp = httpx.post(
                f"{_BASE}/message/sms/send",
                data=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=_TIMEOUT,
            )
        if resp.status_code != 200:
            logger.error("eskiz send failed: HTTP %s %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception:  # noqa: BLE001
        logger.exception("eskiz send failed")
        return False
