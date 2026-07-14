"""Роуты входа через Telegram-бота: start/poll и webhook (с проверкой secret).

Лёгкое приложение с нужными роутерами; get_db → in-memory сессия из фикстуры.
Сеть к Telegram глушим (подменяем _tg_api в сервисе).
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import telegram_login as tl_routes
from app.api.routes import telegram_webhook as wh_routes
from app.config import settings
from app.db.session import get_db
from app.services import tg_login_service


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    monkeypatch.setattr(settings, "login_bot_token", "TESTTOKEN", raising=False)
    monkeypatch.setattr(settings, "login_bot_username", "realtyloginbot", raising=False)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret", raising=False)
    monkeypatch.setattr(tg_login_service, "_tg_api", lambda m, p: {"ok": True, "result": {}})


def _client(db):
    app = FastAPI()
    app.include_router(tl_routes.router, prefix="/api/v1")
    app.include_router(wh_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


def test_full_flow_start_webhook_poll(db):
    client = _client(db)
    r = client.post("/api/v1/auth/telegram/start", json={})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert r.json()["deep_link"].endswith(f"start=login_{code}")

    # pending
    assert client.post("/api/v1/auth/telegram/poll", json={"code": code}).json()["status"] == "pending"

    # webhook: /start (нужен secret-заголовок)
    hdr = {"X-Telegram-Bot-Api-Secret-Token": "s3cret"}
    client.post("/api/v1/telegram/webhook", headers=hdr, json={
        "message": {"chat": {"id": 42}, "text": f"/start login_{code}"}})
    # webhook: подтверждение
    client.post("/api/v1/telegram/webhook", headers=hdr, json={
        "callback_query": {"id": "c1", "data": f"confirm_{code}",
                           "from": {"id": 424242, "first_name": "Тест"},
                           "message": {"chat": {"id": 42}, "message_id": 1}}})

    res = client.post("/api/v1/auth/telegram/poll", json={"code": code})
    assert res.json()["status"] == "confirmed"
    assert res.json()["auth"]["access_token"]


def test_webhook_rejects_bad_secret(db):
    client = _client(db)
    r = client.post("/api/v1/telegram/webhook",
                    headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
                    json={"message": {"chat": {"id": 1}, "text": "/start login_x"}})
    assert r.status_code == 403


def test_start_503_when_not_configured(db, monkeypatch):
    monkeypatch.setattr(settings, "login_bot_token", None, raising=False)
    client = _client(db)
    assert client.post("/api/v1/auth/telegram/start", json={}).status_code == 503
