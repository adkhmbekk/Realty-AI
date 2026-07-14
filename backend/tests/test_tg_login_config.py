"""Настройки входа через Telegram-бота присутствуют и по умолчанию не заданы."""
from app.config import Settings


def test_login_bot_settings_default_none():
    s = Settings(_env_file=None)
    assert s.login_bot_token is None
    assert s.login_bot_username is None
    assert s.telegram_webhook_secret is None


def test_login_bot_empty_string_is_none():
    s = Settings(_env_file=None, LOGIN_BOT_TOKEN="", TELEGRAM_WEBHOOK_SECRET="")
    assert s.login_bot_token is None
    assert s.telegram_webhook_secret is None
