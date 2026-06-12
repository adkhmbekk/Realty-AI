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


def _as_utc(dt: datetime) -> datetime:
    """Дату из БД приводим к aware-UTC: Postgres (прод) отдаёт со смещением,
    SQLite (тесты) — без; иначе сравнение с now(timezone.utc) даёт TypeError."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def agency_is_active(agency) -> bool:
    if agency is None:
        return False
    if agency.status not in ACTIVE_STATUSES:
        return False
    expires_at = agency.subscription_expires_at
    if expires_at is not None and _as_utc(expires_at) < datetime.now(timezone.utc):
        return False
    return True
