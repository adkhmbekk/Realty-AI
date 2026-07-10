"""
Регрессия F-01 (2026-07): вернувшийся личный юзер должен мочь создать агентство
и вступить по коду, даже если ВХОД в этой же сессии уже «сжёг» тот же initData.

Раньше: токены только в памяти → каждый запуск шлёт /auth/telegram, который для
существующего юзера «гасит» initData; затем фронт слал тот же initData в
/agencies/register или /invites/redeem → init_data_replayed. Итог: создать/
вступить мог только новый юзер в первую сессию.

Фикс: эти операции для залогиненного юзера аутентифицируются по JWT (current_user),
а не повторной проверкой initData. Здесь проверяем оба пути.

Плюс F-08: валидация телефона (E.164).
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.config import settings
from app.core import security
from app.core.errors import AppError
from app.repositories import agency_repo, invite_repo, user_repo
from app.services import agency_service, auth_service, invite_service

from tests.test_personal_agencies import _TEST_BOT_TOKEN, _sign_init_data


def _prep(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", _TEST_BOT_TOKEN, raising=False)
    security._seen_init_data.clear()


def _returning_user(db, telegram_id: int):
    """Существующий личный аккаунт (как будто создан в прошлой сессии)."""
    u = user_repo.create(db, telegram_id=telegram_id, role="user", agency_id=None)
    db.commit()
    return u


# ── F-01: регистрация агентства ───────────────────────────────────────────────

def test_register_via_jwt_succeeds_after_login_burned_initdata(db, monkeypatch):
    _prep(monkeypatch)
    user = _returning_user(db, 800001)
    init = _sign_init_data(telegram_id=800001)
    # Вход существующего юзера «гасит» этот initData.
    auth_service.login_with_init_data(db, init)

    # JWT-путь: тот же (уже сожжённый) initData не мешает — личность по пропуску.
    resp = agency_service.register_agency(
        db, init, "Моё агентство", owner_name="Иван",
        phone="+998901234567", current_user=SimpleNamespace(id=user.id, is_active=True),
    )
    assert resp.get("access_token")
    refreshed = user_repo.get_by_telegram_id(db, 800001)
    assert refreshed.role == "agency_admin"
    assert refreshed.is_owner is True
    assert refreshed.agency_id is not None


def test_register_via_initdata_still_blocks_replay(db, monkeypatch):
    """Контроль: запасной initData-путь (без JWT) по-прежнему режет повтор."""
    _prep(monkeypatch)
    _returning_user(db, 800002)
    init = _sign_init_data(telegram_id=800002)
    auth_service.login_with_init_data(db, init)  # «гасит» init
    with pytest.raises(AppError) as exc:
        agency_service.register_agency(
            db, init, "X", owner_name="Y", phone="+998901234567"
        )  # current_user=None → initData-путь
    assert exc.value.key == "init_data_replayed"


# ── F-01: вступление по коду ──────────────────────────────────────────────────

def test_redeem_via_jwt_succeeds_after_login_burned_initdata(db, monkeypatch):
    _prep(monkeypatch)
    agency = agency_repo.create(db, name="Агентство", created_by=None, subscription_days=3650)
    invite_repo.create(
        db, agency_id=agency.id, code="JWTCODE1", role="agent",
        created_by=None, expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        max_uses=5,
    )
    db.commit()

    user = _returning_user(db, 800003)
    init = _sign_init_data(telegram_id=800003)
    auth_service.login_with_init_data(db, init)  # «гасит» init

    resp = invite_service.redeem_invite(
        db, init, "JWTCODE1", current_user=SimpleNamespace(id=user.id, is_active=True)
    )
    assert resp.get("access_token")
    refreshed = user_repo.get_by_telegram_id(db, 800003)
    assert refreshed.agency_id == agency.id


# ── F-08: валидация телефона ──────────────────────────────────────────────────

def test_set_phone_rejects_garbage(db):
    u = user_repo.create(db, telegram_id=800010, role="user", agency_id=None)
    db.commit()
    for bad in ("abc", "12345", "+1", ""):
        with pytest.raises(AppError) as exc:
            auth_service.set_phone(db, u, bad)
        assert exc.value.key == "phone_invalid"


def test_set_phone_accepts_e164(db):
    u = user_repo.create(db, telegram_id=800011, role="user", agency_id=None)
    db.commit()
    out = auth_service.set_phone(db, u, "+998 90 123 45 67")
    assert out.phone == "+998901234567"
    assert out.phone_verified is True
