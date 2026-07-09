"""
Открытая регистрация (юзер-центричная модель, 2026-07).

Раньше вход незнакомца отвечал 403 (инвайт-онли). Теперь любой, кто вошёл через
Telegram, получает ЛИЧНЫЙ аккаунт (role='user', без агентства) и попадает в
личное пространство. Изоляция при этом не нарушается: личный аккаунт не проходит
гварды агентских эндпоинтов (это проверяется отдельно).
"""
from app.config import settings
from app.core import security
from app.repositories import user_repo
from app.services import auth_service

from tests.test_personal_agencies import _TEST_BOT_TOKEN, _sign_init_data


def _prep(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", _TEST_BOT_TOKEN, raising=False)
    security._seen_init_data.clear()


def test_login_creates_personal_account_for_unknown(db, monkeypatch):
    """Незнакомец при входе → создаётся личный аккаунт (role='user', без агентства)."""
    _prep(monkeypatch)
    resp = auth_service.login_with_init_data(db, _sign_init_data(telegram_id=706001))

    u = user_repo.get_by_telegram_id(db, 706001)
    assert u is not None
    assert u.role == "user"
    assert u.agency_id is None
    # Выдана рабочая сессия (не 403).
    assert resp.get("access_token")


def test_login_is_idempotent_for_personal_account(db, monkeypatch):
    """Повторный вход тем же незнакомцем не плодит второй аккаунт."""
    _prep(monkeypatch)
    auth_service.login_with_init_data(db, _sign_init_data(telegram_id=706002))
    security._seen_init_data.clear()
    auth_service.login_with_init_data(db, _sign_init_data(telegram_id=706002))

    # get_by_telegram_id вернул бы ошибку при дубле (scalar_one_or_none), а
    # telegram_id уникален в БД — второй вход не создаёт второй аккаунт.
    u = user_repo.get_by_telegram_id(db, 706002)
    assert u is not None and u.role == "user"
