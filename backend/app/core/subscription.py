"""
Единая проверка «жива ли подписка агентства».

Используется и в зависимостях API (блокировка эндпоинтов), и при входе
(чтобы фронтенд показал экран «подписка неактивна»). Данные при этом не
удаляются — доступ просто приостанавливается, пока агентство не активируют.

Агентство считается активным, если:
  1) его статус — trial или active (frozen / expired блокируются);
  2) срок подписки (subscription_expires_at) либо не задан, либо ещё не истёк.
"""
from datetime import datetime, timezone

ACTIVE_STATUSES = ("trial", "active")


def agency_is_active(agency) -> bool:
    if agency is None:
        return False
    if agency.status not in ACTIVE_STATUSES:
        return False
    expires_at = agency.subscription_expires_at
    if expires_at is not None and expires_at < datetime.now(timezone.utc):
        return False
    return True
