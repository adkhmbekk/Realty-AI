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
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from app.config import settings


class InitDataError(Exception):
    """Данные входа от Telegram не прошли проверку."""


_JWT_ALGORITHM = "HS256"


def _resolve_jwt_secret() -> str:
    """
    Определить секрет для подписи пропусков (JWT).

    Порядок выбора:
      1) если JWT_SECRET задан в настройках/.env — используем его;
      2) иначе берём ранее сохранённый секрет из файла на постоянном диске
         (Docker-том с фотографиями). Благодаря этому секрет НЕ меняется
         между перезапусками, и пользователей больше не «выкидывает» после
         каждого рестарта сервиса;
      3) если такого файла ещё нет — создаём новый секрет и сохраняем его туда.

    Секрет наружу не попадает: файл лежит на томе и не отдаётся через веб
    (эндпоинт фотографий отдаёт только то, что есть в базе данных).
    """
    if settings.jwt_secret:
        return settings.jwt_secret
    try:
        os.makedirs(settings.photos_dir, exist_ok=True)
        secret_file = os.path.join(settings.photos_dir, ".app_jwt_secret")
        if os.path.exists(secret_file):
            with open(secret_file, "r", encoding="utf-8") as fh:
                saved = fh.read().strip()
            if saved:
                return saved
        generated = secrets.token_urlsafe(48)
        with open(secret_file, "w", encoding="utf-8") as fh:
            fh.write(generated)
        try:
            os.chmod(secret_file, 0o600)
        except OSError:
            pass
        return generated
    except Exception:  # noqa: BLE001
        # Крайний случай (нет доступа к диску) — временный секрет на сессию.
        return secrets.token_urlsafe(48)


# Секрет для подписи JWT (стабильный между перезапусками — см. функцию выше).
_JWT_SECRET = _resolve_jwt_secret()


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
        parsed = dict(
            parse_qsl(init_data, strict_parsing=True, keep_blank_values=True)
        )
    except ValueError as exc:
        raise InitDataError("Некорректный формат данных входа") from exc

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InitDataError("В данных входа отсутствует подпись")

    # Секретный ключ выводится из токена бота.
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()

    def _calc(check_string: str) -> str:
        return hmac.new(
            secret_key, check_string.encode(), hashlib.sha256
        ).hexdigest()

    # Строка проверки: все поля (кроме hash), отсортированные по имени.
    keys_all = sorted(parsed)
    dcs_full = "\n".join(f"{key}={parsed[key]}" for key in keys_all)
    # Запасной вариант — без поля signature (некоторые клиенты Telegram не
    # включают его в HMAC). Принимаем вход, если совпал любой из вариантов;
    # на безопасность это не влияет — оба варианта подписаны секретом бота.
    dcs_no_sig = "\n".join(
        f"{key}={parsed[key]}" for key in keys_all if key != "signature"
    )

    is_valid = hmac.compare_digest(_calc(dcs_full), received_hash) or hmac.compare_digest(
        _calc(dcs_no_sig), received_hash
    )
    if not is_valid:
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
