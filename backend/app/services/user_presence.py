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

from sqlalchemy import and_, or_

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


def latest(*dts: Optional[datetime]) -> Optional[datetime]:
    """Самая свежая из дат (МАКСИМУМ), игнорируя None. None — если все пусты.
    Именно максимум, а НЕ «первая непустая»: last_login_at может быть свежее
    last_seen_at (зашёл в агентство/профиль, но heartbeat ещё не обновился)."""
    vals = [v for v in (_as_utc(d) for d in dts) if v is not None]
    return max(vals) if vals else None


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

    Сигнал — МАКСИМУМ из last_seen_at и last_login_at (человек «жив», если свеж
    любой из них). Раньше брали coalesce → устаревший heartbeat «перебивал» свежий
    логин и человек ошибочно уезжал в «спят/не заходят».
    """
    last_active = latest(last_seen_at, last_login_at)
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


def _max_ge(a, b, threshold):
    """MAX(a, b) >= threshold, где NULL трактуется как «минус бесконечность».
    Портабельно (без GREATEST/MAX-агрегата): достаточно, чтобы хоть один >= порога."""
    return or_(a >= threshold, b >= threshold)


def _max_lt(a, b, threshold):
    """MAX(a, b) < threshold: обе даты ниже порога ИЛИ пусты (обе пустые → «never»)."""
    return and_(or_(a.is_(None), a < threshold), or_(b.is_(None), b < threshold))


def engagement_condition(tier: str, now: datetime):
    """SQL-условие для серверного фильтра списка по тиру (работает с пагинацией).

    Использует те же пороги, что и engagement(): МАКСИМУМ из last_seen/last_login
    (а НЕ coalesce). Возвращает None для неизвестного тира (фильтр не применяется).
    """
    if tier not in ENGAGEMENT_TIERS:
        return None
    a = User.last_seen_at
    b = User.last_login_at
    active_from = now - timedelta(days=_ACTIVE_DAYS)
    quiet_from = now - timedelta(days=_QUIET_DAYS)
    asleep_from = now - timedelta(days=_ASLEEP_DAYS)
    if tier == "active":
        return _max_ge(a, b, active_from)
    if tier == "quiet":
        return and_(_max_ge(a, b, quiet_from), _max_lt(a, b, active_from))
    if tier == "asleep":
        return and_(_max_ge(a, b, asleep_from), _max_lt(a, b, quiet_from))
    # never: давно (< asleep-порога обе) или ни разу (обе пусты).
    return _max_lt(a, b, asleep_from)
