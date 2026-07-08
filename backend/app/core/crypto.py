"""
Шифрование секретов в базе (Fernet, библиотека cryptography).

Сейчас применяется к Google refresh-токенам (таблица agency_sheets): они дают
доступ к таблице агентства, поэтому в базе/бэкапе должны лежать зашифрованными.
Ключ берётся из settings.app_encryption_key и хранится в .env на сервере — ВНЕ
базы и вне бэкапов.

Формат: зашифрованные значения получают префикс "enc:". Значения без префикса
считаются «старыми» (открытый текст) и возвращаются как есть — это позволяет
перейти на шифрование плавно, ничего не ломая (старые токены доразово
перешифровываются отдельно, см. [[security-roadmap]]).

Если ключ не задан — шифрование отключено (значения хранятся как есть). Это нужно
для локальной разработки и тестов; на сервере ключ обязателен.
"""
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger("uvicorn.error")

_PREFIX = "enc:"
_fernet = None
_init_done = False


def _get_fernet():
    """Лениво собрать Fernet из ключа. None — если ключ не задан/неверный."""
    global _fernet, _init_done
    if _init_done:
        return _fernet
    _init_done = True
    key = settings.app_encryption_key
    if not key:
        logger.warning("APP_ENCRYPTION_KEY не задан — секреты в БД НЕ шифруются.")
        return None
    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:  # noqa: BLE001
        logger.error("Неверный APP_ENCRYPTION_KEY (%s) — шифрование отключено.", exc)
        _fernet = None
    return _fernet


def encrypt(value: Optional[str]) -> Optional[str]:
    """Зашифровать строку (→ 'enc:...'). Нет ключа или уже зашифровано — как есть."""
    if value is None:
        return None
    if value.startswith(_PREFIX):
        return value
    f = _get_fernet()
    if f is None:
        # #6 fail-closed: в проде запрещаем хранить секрет открытым текстом —
        # иначе Google refresh-токены молча легли бы в БД/бэкап в открытом виде.
        if settings.is_prod:
            raise RuntimeError(
                "APP_ENCRYPTION_KEY обязателен при ENV=prod: отказываюсь хранить "
                "секрет в открытом виде в БД."
            )
        return value
    return _PREFIX + f.encrypt(value.encode()).decode()


def decrypt(value: Optional[str]) -> Optional[str]:
    """Расшифровать строку. Старое значение без префикса — вернуть как есть. Если
    расшифровать нельзя (нет ключа/битый шифртекст) — None (вызывающий код увидит
    «секрет недоступен», а не упадёт)."""
    if value is None:
        return None
    if not value.startswith(_PREFIX):
        return value  # legacy: открытый текст
    f = _get_fernet()
    if f is None:
        logger.error("В БД есть зашифрованный секрет, но APP_ENCRYPTION_KEY не задан.")
        return None
    try:
        return f.decrypt(value[len(_PREFIX):].encode()).decode()
    except Exception as exc:  # noqa: BLE001
        logger.error("Не удалось расшифровать секрет: %s", exc)
        return None
