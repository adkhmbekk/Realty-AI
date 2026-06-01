"""
Базовые «дымовые» тесты: проверяют ключевую логику без обращения к базе данных.

Их задача — поймать грубые поломки (например, сломался вход) до того, как
изменения попадут в main. Запускаются автоматически в CI на каждый PR.
"""
import pytest

from app.core import security


# ─── Пропуска (JWT) ──────────────────────────────────────────────────────
def test_jwt_roundtrip():
    token = security.create_access_token({"user_id": 123})
    payload = security.decode_access_token(token)
    assert payload is not None
    assert payload["user_id"] == 123


def test_decode_invalid_token_returns_none():
    assert security.decode_access_token("definitely-not-a-valid-token") is None


# ─── Проверка данных входа Telegram ──────────────────────────────────────
def test_validate_init_data_rejects_empty():
    with pytest.raises(security.InitDataError):
        security.validate_init_data("", "dummy-bot-token")


def test_validate_init_data_rejects_tampered():
    # Подпись (hash) заведомо неверная — данные должны быть отклонены.
    with pytest.raises(security.InitDataError):
        security.validate_init_data("user=%7B%22id%22%3A1%7D&hash=deadbeef", "dummy-bot-token")
