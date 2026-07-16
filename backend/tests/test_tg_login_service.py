"""tg_login_service: генерация кода, обработка апдейтов бота, poll → сессия.

Сеть к Telegram не трогаем: подменяем отправителей сообщений заглушками.
"""
import re

import pytest

from app.config import settings
from app.repositories import tg_login_repo, user_repo
from app.services import tg_login_service


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    monkeypatch.setattr(settings, "login_bot_token", "TESTTOKEN", raising=False)
    monkeypatch.setattr(settings, "login_bot_username", "realtyloginbot", raising=False)
    # Глушим реальные вызовы Telegram API.
    monkeypatch.setattr(tg_login_service, "_tg_api", lambda method, payload: {"ok": True, "result": {}})


def test_start_login_returns_code_and_link(db):
    out = tg_login_service.start_login(db)
    # Ровно 32 hex-символа (128 бит из token_hex) — а не просто «длинная строка».
    assert re.fullmatch(r"[0-9a-f]{32}", out["code"])
    assert out["deep_link"] == f"https://t.me/realtyloginbot?start=login_{out['code']}"
    assert out["expires_in"] == tg_login_service.CODE_TTL_SECONDS
    # РЕГРЕССИЯ: start_login ДОЛЖЕН сам закоммитить код. Иначе в проде (get_db не
    # коммитит на выходе, webhook/poll — в другой сессии) код теряется. Проверяем
    # так: после rollback код обязан остаться — значит commit был.
    db.rollback()
    assert tg_login_repo.get_by_code(db, out["code"]) is not None


def test_start_login_503_when_not_configured(db, monkeypatch):
    from app.core.errors import AppError
    monkeypatch.setattr(settings, "login_bot_token", None, raising=False)
    with pytest.raises(AppError):
        tg_login_service.start_login(db)


def test_poll_pending_then_confirmed(db):
    code = tg_login_service.start_login(db)["code"]
    db.commit()
    assert tg_login_service.poll(db, code)["status"] == "pending"

    # Симулируем /start в боте (шлёт сообщение с кнопкой) и нажатие «Подтвердить».
    tg_login_service.handle_update(db, {
        "message": {"chat": {"id": 999}, "text": f"/start login_{code}"}
    })
    db.commit()
    tg_login_service.handle_update(db, {
        "callback_query": {
            "id": "cb1",
            "data": f"confirm_{code}",
            "from": {"id": 777001, "first_name": "Оля", "last_name": "Ким"},
            "message": {"chat": {"id": 999}, "message_id": 5},
        }
    })
    db.commit()

    res = tg_login_service.poll(db, code)
    assert res["status"] == "confirmed"
    assert res["auth"]["access_token"]
    assert user_repo.get_by_telegram_id(db, 777001) is not None

    # Одноразовость: повторный poll уже не отдаёт сессию.
    assert tg_login_service.poll(db, code)["status"] != "confirmed"


def test_unknown_code_is_pending(db):
    assert tg_login_service.poll(db, "doesnotexist")["status"] == "pending"
