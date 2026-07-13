"""
Вход через Google (нативное приложение, вне Telegram).

Google/Apple-юзер не имеет telegram_id — его личность определяется по google_sub
(стабильный идентификатор Google-аккаунта). Первый вход создаёт ЛИЧНЫЙ аккаунт
(role='user', без агентства) — так же, как открытая регистрация из Telegram
(см. test_open_registration). Связывание с Telegram-аккаунтом того же человека по
email/телефону здесь НЕ делаем (риск угона) — это отдельный этап (телефон-якорь).

Проверка подписи Google ID-token (JWKS) тестируется отдельно; здесь сервис
получает уже проверенные claims, поэтому сеть не нужна.
"""
from app.repositories import user_repo
from app.services import auth_service


def test_google_login_creates_personal_account_for_new_user(db):
    """Новый Google-юзер → личный аккаунт (role='user', без агентства, без telegram_id)."""
    resp = auth_service.login_with_google(
        db,
        google_sub="google-oauth2|1001",
        email="new@example.com",
        first_name="Иван",
        last_name="Петров",
    )

    u = user_repo.get_by_google_sub(db, "google-oauth2|1001")
    assert u is not None
    assert u.role == "user"
    assert u.agency_id is None
    assert u.telegram_id is None
    assert u.google_sub == "google-oauth2|1001"
    assert u.email == "new@example.com"
    # Выдана рабочая сессия.
    assert resp.get("access_token")
    assert resp.get("refresh_token")


def test_google_login_is_idempotent(db):
    """Повторный вход тем же google_sub не плодит второй аккаунт и возвращает того же."""
    auth_service.login_with_google(db, google_sub="google-oauth2|1002")
    auth_service.login_with_google(db, google_sub="google-oauth2|1002")

    # get_by_google_sub упал бы на дубле (scalar_one_or_none), а google_sub
    # уникален в БД — второй вход не создаёт второй аккаунт.
    u = user_repo.get_by_google_sub(db, "google-oauth2|1002")
    assert u is not None and u.role == "user"
