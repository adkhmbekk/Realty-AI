"""
Роуты нативного входа: POST /auth/google и /auth/apple.

Проверяем ВСЮ обвязку роута (verifier → сервис → выдача пропуска), не трогая сеть:
подпись токена подменяем моком verifier'а. Отдельно — что без сконфигурированных
client_id роут отвечает 503, а на невалидный токен — 401.

Поднимаем лёгкое приложение с одним auth-роутером и подменяем get_db на in-memory
сессию из фикстуры (стиль test_db_retry). AppError наследует HTTPException, поэтому
статусы отдаёт и минимальное приложение.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import auth as auth_routes
from app.config import settings
from app.core.oauth_verify import OAuthError
from app.db.session import get_db
from app.repositories import user_repo


def _client(db):
    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


def test_google_login_route_creates_user_and_issues_token(db, monkeypatch):
    # Сконфигурирован наш client_id (иначе 503).
    monkeypatch.setattr(settings, "google_ios_client_id", "test-aud", raising=False)
    # Подпись/aud проверяет verifier — мокаем его проверенными claims.
    monkeypatch.setattr(
        auth_routes,
        "verify_google_id_token",
        lambda token, auds: {
            "sub": "google-1",
            "email": "ivan@example.com",
            "given_name": "Иван",
            "family_name": "Петров",
        },
    )
    client = _client(db)

    r = client.post("/api/v1/auth/google", json={"id_token": "whatever"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["access_token"]
    assert data["user"]["role"] == "user"
    assert data["user"]["email"] == "ivan@example.com"
    assert data["user"]["telegram_id"] is None

    # Пропуск рабочий: /auth/me по нему проходит.
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer " + data["access_token"]},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "ivan@example.com"

    # Аккаунт реально создан.
    assert user_repo.get_by_google_sub(db, "google-1") is not None


def test_google_login_route_503_when_not_configured(db, monkeypatch):
    # Ни один google_*_client_id не задан → вход через Google не сконфигурирован.
    monkeypatch.setattr(settings, "google_ios_client_id", None, raising=False)
    monkeypatch.setattr(settings, "google_android_client_id", None, raising=False)
    monkeypatch.setattr(settings, "google_web_client_id", None, raising=False)
    client = _client(db)

    r = client.post("/api/v1/auth/google", json={"id_token": "x"})
    assert r.status_code == 503


def test_google_login_route_401_on_invalid_token(db, monkeypatch):
    monkeypatch.setattr(settings, "google_ios_client_id", "test-aud", raising=False)

    def _reject(token, auds):
        raise OAuthError()

    monkeypatch.setattr(auth_routes, "verify_google_id_token", _reject)
    client = _client(db)

    r = client.post("/api/v1/auth/google", json={"id_token": "forged"})
    assert r.status_code == 401


def test_apple_login_route_creates_user(db, monkeypatch):
    monkeypatch.setattr(settings, "apple_bundle_id", "com.realtyai.app", raising=False)
    monkeypatch.setattr(
        auth_routes,
        "verify_apple_identity_token",
        lambda token, auds: {"sub": "apple-1", "email": "a@icloud.com"},
    )
    client = _client(db)

    r = client.post(
        "/api/v1/auth/apple",
        json={"identity_token": "x", "first_name": "Али", "last_name": "Валиев"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]
    u = user_repo.get_by_apple_sub(db, "apple-1")
    assert u is not None and u.role == "user" and u.full_name == "Али Валиев"
