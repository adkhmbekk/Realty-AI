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
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from app.config import settings


class InitDataError(Exception):
    """Данные входа от Telegram не прошли проверку.

    Несёт ключ перевода (key) для локализованного сообщения пользователю и
    запасной русский текст (для логов).
    """

    def __init__(self, key: str, message: str = ""):
        self.key = key
        super().__init__(message or key)


_JWT_ALGORITHM = "HS256"


def _read_secret_from_dir(directory: str) -> Optional[str]:
    """Прочитать сохранённый секрет из <directory>/.app_jwt_secret (или None)."""
    try:
        secret_file = os.path.join(directory, ".app_jwt_secret")
        if os.path.exists(secret_file):
            with open(secret_file, "r", encoding="utf-8") as fh:
                saved = fh.read().strip()
            return saved or None
    except Exception:  # noqa: BLE001
        return None
    return None


def _write_secret_to_dir(directory: str, value: str) -> bool:
    """Сохранить секрет в <directory>/.app_jwt_secret с правами 0600 (True/False)."""
    try:
        os.makedirs(directory, exist_ok=True)
        secret_file = os.path.join(directory, ".app_jwt_secret")
        with open(secret_file, "w", encoding="utf-8") as fh:
            fh.write(value)
        try:
            os.chmod(secret_file, 0o600)
        except OSError:
            pass
        return True
    except Exception:  # noqa: BLE001
        return False


def _resolve_jwt_secret() -> str:
    """
    Определить секрет для подписи пропусков (JWT).

    Порядок выбора:
      1) если JWT_SECRET задан в настройках/.env — используем его (рекомендуется
         для прод-развёртывания, особенно при нескольких серверах);
      2) иначе берём ранее сохранённый секрет из ВЫДЕЛЕННОЙ папки секретов
         (settings.secret_dir — отдельный том, НЕ совпадающий с папкой фото и
         НЕ попадающий в бэкапы). Благодаря этому секрет не «выкидывает»
         пользователей между перезапусками и при этом не лежит рядом с
         пользовательским контентом и не утекает с резервными копиями;
      3) для обратной совместимости — если в выделенной папке секрета ещё нет,
         но он остался в старом месте (photos_dir), переносим его туда и
         подчищаем старый файл;
      4) если секрета нигде нет — создаём новый и сохраняем в secret_dir;
      5) крайний случай (нет доступа к диску) — временный секрет на сессию.

    Секрет наружу не попадает: папка секретов не отдаётся через веб.
    """
    if settings.jwt_secret:
        return settings.jwt_secret

    secret_dir = settings.secret_dir
    legacy_dir = settings.photos_dir

    # 2) Уже сохранённый секрет в выделенной папке.
    existing = _read_secret_from_dir(secret_dir)
    if existing:
        return existing

    # 3) Обратная совместимость: перенос секрета из старого места (papka фото).
    legacy = _read_secret_from_dir(legacy_dir)
    if legacy:
        if _write_secret_to_dir(secret_dir, legacy):
            # Старую копию удаляем, чтобы секрет не оставался на томе фото/в бэкапах.
            try:
                os.remove(os.path.join(legacy_dir, ".app_jwt_secret"))
            except OSError:
                pass
        return legacy

    # 4) Нового секрета ещё нет — генерируем и сохраняем в выделенной папке.
    generated = secrets.token_urlsafe(48)
    _write_secret_to_dir(secret_dir, generated)
    return generated


# Секрет для подписи JWT (стабильный между перезапусками — см. функцию выше).
_JWT_SECRET = _resolve_jwt_secret()


# ─── Защита от повторного использования initData (anti-replay) ──────────────
# Telegram подписывает initData, но без доп. защиты одни и те же данные можно
# переиграть много раз, пока они «свежие» (см. init_data_max_age_seconds).
# Здесь мы запоминаем подпись (hash) уже принятых initData до момента их
# протухания и отклоняем повторы. Хранилище — в памяти процесса (этого
# достаточно для однопроцессного развёртывания за туннелем).
_replay_lock = threading.Lock()
_seen_init_data: "dict[str, float]" = {}


def _replay_check_and_remember(signature: str, expires_at: float) -> bool:
    """
    Вернуть True, если подпись ВИДЕЛИ раньше (это повтор → надо отклонить).
    Иначе запомнить её до expires_at и вернуть False. Заодно чистим протухшие.
    """
    now = time.time()
    with _replay_lock:
        # Лёгкая периодическая чистка протухших записей.
        if len(_seen_init_data) > 2048:
            for key, exp in list(_seen_init_data.items()):
                if exp <= now:
                    _seen_init_data.pop(key, None)
        seen_until = _seen_init_data.get(signature)
        if seen_until is not None and seen_until > now:
            return True
        _seen_init_data[signature] = expires_at
        return False


# ─── Проверка данных Telegram (initData) ────────────────────────────────────

def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,
    anti_replay: bool = True,
) -> dict:
    """
    Проверить подпись initData по алгоритму Telegram и вернуть данные
    пользователя. Бросает InitDataError, если что-то не так.
    """
    from urllib.parse import parse_qsl

    if not init_data:
        raise InitDataError("init_data_empty", "Пустые данные входа")

    try:
        parsed = dict(
            parse_qsl(init_data, strict_parsing=True, keep_blank_values=True)
        )
    except ValueError as exc:
        raise InitDataError("init_data_bad_format", "Некорректный формат данных входа") from exc

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InitDataError("init_data_no_signature", "В данных входа отсутствует подпись")

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
        raise InitDataError("init_data_bad_signature", "Подпись данных входа недействительна")

    # Проверка свежести (защита от повторного использования старых данных).
    auth_date_raw = parsed.get("auth_date", "0")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise InitDataError("init_data_bad_date", "Некорректная дата входа") from exc

    if max_age_seconds and (time.time() - auth_date) > max_age_seconds:
        raise InitDataError("init_data_expired", "Данные входа устарели, откройте приложение заново")

    # Срок жизни записи в хранилище повторов: до естественного протухания initData.
    ttl = max_age_seconds if max_age_seconds else 3600
    replay_expires_at = auth_date + ttl

    # Защита от повторного использования (anti-replay): одну и ту же подпись
    # принимаем только один раз — до момента её естественного протухания.
    # Это закрывает переигрывание перехваченного initData в пределах окна
    # свежести. Проверяем только ПОСЛЕ успешной проверки подписи и срока, чтобы
    # неудачные/просроченные попытки не засоряли хранилище.
    #
    # ВАЖНО: если anti_replay=False, подпись НЕ запоминается здесь — вызывающий
    # код «погасит» её сам (security.remember_replay), но только когда реально
    # выдаёт сессию. Это нужно для связки login→redeem: вход незнакомца сначала
    # отвечает 403, и нельзя «сжигать» его initData, иначе следующий за ним
    # запрос вступления по коду (с тем же initData) ложно посчитается повтором.
    if anti_replay:
        if _replay_check_and_remember(received_hash, replay_expires_at):
            raise InitDataError(
                "init_data_replayed",
                "Эти данные входа уже использованы, откройте приложение заново",
            )

    # Поле user — это JSON-строка с информацией о пользователе.
    try:
        user = json.loads(parsed.get("user", "{}"))
    except json.JSONDecodeError as exc:
        raise InitDataError("init_data_bad_user", "Некорректные данные пользователя") from exc

    if not user.get("id"):
        raise InitDataError("init_data_no_user_id", "В данных входа нет идентификатора пользователя")

    return {
        "user": user,
        "auth_date": auth_date,
        # Для отложенного «гашения» повтора вызывающим кодом (anti_replay=False).
        "init_data_hash": received_hash,
        "replay_expires_at": replay_expires_at,
    }


def remember_replay(signature: str, expires_at: float) -> bool:
    """
    Пометить подпись initData как использованную (для anti_replay=False, когда
    решение «гасить ли повтор» принимает вызывающий код — например, вход только
    при реальной выдаче сессии). Возвращает True, если подпись уже видели раньше
    (это повтор → надо отклонить), иначе запоминает её и возвращает False.
    """
    return _replay_check_and_remember(signature, expires_at)


# ─── JWT-пропуска ───────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    """Создать подписанный пропуск (JWT) с заданными данными и сроком жизни."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode["exp"] = expire
    to_encode["type"] = "access"
    return jwt.encode(to_encode, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """
    Создать долгоживущий refresh-пропуск. Им можно обновить короткий access-токен
    БЕЗ повторной проверки initData (которое Telegram «протухает» через час).
    Это решает «тихий тупик»: сессия дольше часа больше не упирается в стену.
    """
    to_encode = {
        "user_id": data.get("user_id"),
        "epoch": data.get("epoch", 0),
        "type": "refresh",
    }
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.refresh_expire_minutes
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Проверить пропуск и вернуть его содержимое. None — если недействителен."""
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def decode_refresh_token(token: str) -> Optional[dict]:
    """
    Проверить refresh-пропуск. Возвращает содержимое только если это именно
    refresh-токен (а не access) и он не истёк. Иначе None.
    """
    payload = decode_access_token(token)
    if payload is None or payload.get("type") != "refresh":
        return None
    return payload
