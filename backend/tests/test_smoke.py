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



# ─── Защита импорта фотографий (только Telegram + без внутренней сети) ────
from fastapi import HTTPException  # noqa: E402

from app.services import photo_service, telegram_service  # noqa: E402


def test_is_telegram_url():
    assert photo_service._is_telegram_url("https://t.me/some_channel/42")
    assert photo_service._is_telegram_url("https://telegram.me/some_channel/42")
    assert not photo_service._is_telegram_url("https://example.com/post")
    assert not photo_service._is_telegram_url("https://evil-t.me.attacker.com/x")


def test_assert_public_url_blocks_internal_and_bad_scheme():
    for bad in (
        "http://localhost/x",
        "http://127.0.0.1/x",
        "http://10.0.0.5/x",
        "http://169.254.169.254/latest/meta-data",
        "ftp://example.com/x",
    ):
        with pytest.raises(HTTPException):
            photo_service._assert_public_url(bad)


# ─── Сборка альбома для бота (без сети) ──────────────────────────────────
def test_telegram_multipart_structure():
    body, content_type = telegram_service._build_multipart(
        {"chat_id": "1", "media": "[]"},
        [("photo0", "photo0.jpg", "image/jpeg", b"binarydata")],
    )
    assert content_type.startswith("multipart/form-data; boundary=")
    assert b'name="chat_id"' in body
    assert b'name="photo0"; filename="photo0.jpg"' in body
    assert b"binarydata" in body



# ─── Хелперы графиков аналитики (без сети/БД) ────────────────────────────
import datetime as _dt  # noqa: E402

from app.services import apartment_service as _aptsvc  # noqa: E402


def test_bucket_starts_counts():
    assert len(_aptsvc._bucket_starts("day", 7)) == 7
    assert len(_aptsvc._bucket_starts("month", 6)) == 6
    # Корзины идут по возрастанию (старые -> новые).
    days = _aptsvc._bucket_starts("day", 5)
    assert days == sorted(days)


def test_bucket_label_formats():
    assert _aptsvc._bucket_label("day", _dt.date(2026, 6, 1)) == "01.06"
    assert _aptsvc._bucket_label("month", _dt.date(2026, 6, 1)) == "июн"
