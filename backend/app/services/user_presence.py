"""
Присутствие и вовлечённость пользователей — для витрины «юзеры прошки» у
владельца платформы.

Считает по уже существующим полям users (новые таблицы НЕ нужны):
  - last_seen_at  — последний heartbeat (человек был в приложении). Основной сигнал.
  - last_login_at — запасной сигнал для тех, кто заходил ещё ДО появления heartbeat
                    (колонка last_seen_at добавлена миграцией 0031).

Два независимых измерения:
  • presence — присутствие «прямо сейчас» (минуты): online / recent / offline;
  • engagement — вовлечённость «в целом» (дни): active / quiet / asleep / never.

Пороги — единый источник правды (эти же значения переиспользуют SQL-фильтр и
агрегатную статистику), чтобы карточка, точка тира и сводка не разъезжались.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_

from app.db.models.user import User

# ── Присутствие «в сети» (минуты) ────────────────────────────────────────────
# online: свежий heartbeat (совпадает с порогом «в сети» у агентств — фронт пингует
# ~раз в 30с, 3 минуты терпят пару пропущенных пингов).
ONLINE_WITHIN = timedelta(minutes=3)
# recent («был только что»): первая минута ПОСЛЕ того, как человек вышел
# (heartbeat перестал приходить). Дальше показываем точное время.
RECENT_WITHIN = timedelta(minutes=4)

# ── Вовлечённость «светофор» (дни) ───────────────────────────────────────────
_ACTIVE_DAYS = 3    # заходил за последние N дней → 🟢 активные
_QUIET_DAYS = 10    # 3–10 дней тишины → 🟡 притихли
_ASLEEP_DAYS = 30   # 10–30 дней → 🟠 спят; больше или ни разу → 🔴 не заходят

ENGAGEMENT_TIERS = ("active", "quiet", "asleep", "never")


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def presence(last_seen_at: Optional[datetime], now: datetime) -> str:
    """online / recent / offline — по свежести последнего heartbeat."""
    seen = _as_utc(last_seen_at)
    if seen is None:
        return "offline"
    age = now - seen
    if age <= ONLINE_WITHIN:
        return "online"
    if age <= RECENT_WITHIN:
        return "recent"
    return "offline"


def engagement(
    last_seen_at: Optional[datetime],
    last_login_at: Optional[datetime],
    now: datetime,
) -> str:
    """active / quiet / asleep / never — по давности последнего присутствия.

    Сигнал — last_seen_at, с фолбэком на last_login_at (кто заходил до heartbeat).
    """
    last_active = _as_utc(last_seen_at) or _as_utc(last_login_at)
    if last_active is None:
        return "never"
    # Точные дельты (а НЕ .days), чтобы совпадать с SQL-фильтром engagement_condition.
    age = now - last_active
    if age <= timedelta(days=_ACTIVE_DAYS):
        return "active"
    if age <= timedelta(days=_QUIET_DAYS):
        return "quiet"
    if age <= timedelta(days=_ASLEEP_DAYS):
        return "asleep"
    return "never"


def engagement_condition(tier: str, now: datetime):
    """SQL-условие для серверного фильтра списка по тиру (работает с пагинацией).

    Использует те же пороги, что и engagement(): coalesce(last_seen, last_login).
    Возвращает None для неизвестного тира (фильтр тогда просто не применяется).
    """
    if tier not in ENGAGEMENT_TIERS:
        return None
    last_active = func.coalesce(User.last_seen_at, User.last_login_at)
    active_from = now - timedelta(days=_ACTIVE_DAYS)
    quiet_from = now - timedelta(days=_QUIET_DAYS)
    asleep_from = now - timedelta(days=_ASLEEP_DAYS)
    if tier == "active":
        return last_active >= active_from
    if tier == "quiet":
        return (last_active >= quiet_from) & (last_active < active_from)
    if tier == "asleep":
        return (last_active >= asleep_from) & (last_active < quiet_from)
    # never: давно (> asleep-порога) или ни разу.
    return or_(last_active < asleep_from, last_active.is_(None))
