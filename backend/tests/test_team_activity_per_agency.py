"""#4 — Экран «Активность команды» (agency_usage_service.activity) показывает
присутствие сотрудников ПО-АГЕНТСКИ: онлайн/последняя активность берутся из
agency_memberships.last_seen_at (присутствие ИМЕННО в этом агентстве), а НЕ из
глобального users.last_seen_at. Так статус совпадает с карточкой юзера у
владельца платформы (platform_service) и означает «активен в ЭТОМ агентстве».
"""
from datetime import datetime, timedelta, timezone

from app.db.models.agency import Agency
from app.repositories import agency_membership_repo, user_repo
from app.services import agency_usage_service


def _agency(db):
    a = Agency(name="Тест", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(a)
    db.commit()
    return a


def _register_pg_funcs(db):
    """SQLite не знает PG-функций date_trunc/timezone (дневная разбивка в activity()).
    Регистрируем их как passthrough — на присутствие сотрудников они не влияют, а без
    них запрос не компилируется даже при нуле объектов (тут объектов нет)."""
    raw = db.connection().connection.driver_connection
    raw.create_function("date_trunc", 2, lambda unit, ts: ts)
    raw.create_function("timezone", 2, lambda tz, ts: ts)


def test_online_is_per_agency_not_global(db):
    """Глобально «в сети», но в этом агентстве давно → сотрудник НЕ online."""
    _register_pg_funcs(db)
    now = datetime.now(timezone.utc)
    a = _agency(db)
    u = user_repo.create(db, telegram_id=111, role="agent", agency_id=a.id)
    u.last_seen_at = now          # глобально активен прямо сейчас
    u.last_login_at = now
    db.commit()
    agency_membership_repo.create(db, user_id=u.id, agency_id=a.id, role="agent")
    m = agency_membership_repo.get(db, u.id, a.id)
    m.last_seen_at = now - timedelta(days=3)  # но в ЭТОМ агентстве — 3 дня назад
    db.commit()

    out = agency_usage_service.activity(db, a.id)
    emp = next(e for e in out.employees if e.user_id == u.id)
    assert emp.online is False, "глобально онлайн, но в агентстве давно — не online"
    assert out.online_users == 0
    # last_active_at/last_seen_at — из членства (per-agency), не глобальный seen.
    assert emp.last_active_at == m.last_seen_at
    assert emp.last_seen_at == m.last_seen_at
    # Глобальный вход по-прежнему показываем отдельно.
    assert emp.last_login_at == u.last_login_at


def test_presence_in_this_agency_marks_online(db):
    """Отметка присутствия В агентстве (heartbeat) → сотрудник online здесь."""
    _register_pg_funcs(db)
    now = datetime.now(timezone.utc)
    a = _agency(db)
    u = user_repo.create(db, telegram_id=222, role="agent", agency_id=a.id)
    u.last_seen_at = now - timedelta(days=10)  # глобально «давно» — не важно
    db.commit()
    agency_membership_repo.create(db, user_id=u.id, agency_id=a.id, role="agent")
    agency_membership_repo.touch_last_seen(db, u.id, a.id, now)  # присутствие тут — сейчас

    out = agency_usage_service.activity(db, a.id)
    emp = next(e for e in out.employees if e.user_id == u.id)
    assert emp.online is True
    assert out.online_users == 1
