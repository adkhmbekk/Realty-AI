"""
Лёгкий мониторинг сбоев сервера.

Идея: любую НЕПРЕДВИДЕННУЮ ошибку (500) мы пишем в лог и, если настроено,
шлём краткое уведомление суперадмину в бот. Так о сбоях у агентств можно
узнать сразу, без сторонних сервисов и затрат.

Защита от спама: одинаковые ошибки (один тип + путь + текст) не шлются чаще,
чем раз в _THROTTLE_SECONDS.

При желании это легко заменить/дополнить внешним сервисом (например, Sentry):
обработчик ошибок в одном месте — main.py.
"""
import logging
import time
import traceback
from typing import Optional

from app.config import settings
from app.services import telegram_service

logger = logging.getLogger("uvicorn.error")

# Не повторять одно и то же уведомление чаще, чем раз в 5 минут.
_THROTTLE_SECONDS = 300
_MAX_MESSAGE = 3500
# Сигнатура ошибки -> время последней отправки (в памяти процесса).
_last_sent: dict[str, float] = {}


def _signature(exc: BaseException, path: str) -> str:
    return f"{type(exc).__name__}|{path}|{str(exc)[:100]}"


def report_error(
    exc: BaseException,
    *,
    path: str = "",
    method: str = "",
    agency_id: Optional[int] = None,
    now: Optional[float] = None,
) -> bool:
    """
    Залогировать необработанную ошибку и (если включено и настроено) уведомить
    суперадмина в бот. Возвращает True, если уведомление поставлено в отправку.
    """
    logger.error("Необработанная ошибка [%s %s]: %s", method, path, exc, exc_info=True)

    if not settings.error_alerts_enabled:
        return False
    superadmin_ids = settings.superadmin_ids()
    if not superadmin_ids or not telegram_service.is_configured():
        return False

    now = now if now is not None else time.time()
    sig = _signature(exc, path)
    last = _last_sent.get(sig)
    if last is not None and (now - last) < _THROTTLE_SECONDS:
        return False
    _last_sent[sig] = now

    summary = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    parts = ["⚠️ Сбой на сервере"]
    if method or path:
        parts.append(f"{method} {path}".strip())
    if agency_id is not None:
        parts.append(f"Агентство: {agency_id}")
    parts.append(summary)
    text = "\n".join(parts)[:_MAX_MESSAGE]

    telegram_service.notify_async(sorted(superadmin_ids), text)
    return True
