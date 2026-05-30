"""
Ядро безопасности.

Здесь две независимые задачи:
  1) validate_init_data — проверка подлинности данных, которые Telegram
     передаёт в Mini App (initData). Это гарантирует, что перед нами
     действительно тот Telegram-пользователь, за кого он себя выдаёт.
  2) JWT-пропуска — создание и проверка короткоживущего токена, который
     мы выдаём после успешного входа и который клиент присылает в каждом
     последующем запросе.
"""
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from app.config import settings


class InitDataError(Exception):
    """Данные входа от Telegram не прошли проверку."""


# Секрет для подписи JWT. Если не задан в настройках — генерируем случайный.
# (При перезапуске сервиса он сменится, и старые токены станут недействительны —
#  для локальной разработки это нормально.)
_JWT_SECRET = settings.jwt_secret or secrets.token_urlsafe(32)
_JWT_ALGORITHM = "HS256"


# ─── Проверка данных Telegram (initData) ────────────────────────────────────

def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,
) -> dict:
    """
    Проверить подпись initData по алгоритму Telegram и вернуть данные
    пользователя. Бросает InitDataError, если что-то не так.
    """
    from urllib.parse import parse_qsl

    if not init_data:
        raise InitDataError("Пустые данные входа")

    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError as exc:
        raise InitDataError("Некорректный формат данных входа") from exc

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InitDataError("В данных входа отсутствует подпись")

    # Строка для проверки: все поля, отсортированные по имени, через перевод строки.
    data_check_string = "\n".join(f"{key}={parsed[key]}" for key in sorted(parsed))

    # Секретный ключ выводится из токена бота.
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    # Сравнение, устойчивое к атакам по времени.
    if not hmac.compare_digest(computed_hash, received_hash):
        raise InitDataError("Подпись данных входа недействительна")

    # Проверка свежести (защита от повторного использования старых данных).
    auth_date_raw = parsed.get("auth_date", "0")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise InitDataError("Некорректная дата входа") from exc

    if max_age_seconds and (time.time() - auth_date) > max_age_seconds:
        raise InitDataError("Данные входа устарели, откройте приложение заново")

    # Поле user — это JSON-строка с информацией о пользователе.
    try:
        user = json.loads(parsed.get("user", "{}"))
    except json.JSONDecodeError as exc:
        raise InitDataError("Некорректные данные пользователя") from exc

    if not user.get("id"):
        raise InitDataError("В данных входа нет идентификатора пользователя")

    return {"user": user, "auth_date": auth_date}


# ─── JWT-пропуска ───────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    """Создать подписанный пропуск (JWT) с заданными данными и сроком жизни."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Проверить пропуск и вернуть его содержимое. None — если недействителен."""
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
