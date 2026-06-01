"""
Конфигурация backend. Все настройки читаются из переменных окружения
(или из файла .env). Никаких секретов в коде.

Часть 1B: добавились настройки для входа через Telegram.
Все они НЕОБЯЗАТЕЛЬНЫ, чтобы проект запускался даже без токена бота
(тогда вход через Telegram просто вернёт понятную ошибку, а структуру
API всё равно можно посмотреть в /docs).
"""
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ─── База данных ────────────────────────────────────────────────────
    database_url: str = "postgresql+psycopg://realty:realty_local_dev@db:5432/realty"

    # ─── Telegram / Безопасность ────────────────────────────────────────
    # Токен бота от @BotFather. Нужен для проверки подлинности входа.
    bot_token: Optional[str] = None
    # Секрет для подписи пропусков (JWT). Если не задан — сгенерируется
    # случайный при старте (для локальной разработки этого достаточно).
    jwt_secret: Optional[str] = None
    # Сколько минут действует выданный пропуск (по умолчанию 12 часов).
    jwt_expire_minutes: int = 720
    # Telegram ID владельца платформы. Этот человек станет суперадмином
    # автоматически при запуске.
    superadmin_telegram_id: Optional[int] = None
    # Имя бота без @ (например "my_realty_bot"). Нужно только для красивой
    # ссылки-приглашения вида https://t.me/<bot>?startapp=<код>. Если не задано —
    # приглашение всё равно работает, просто сотрудник вводит код вручную.
    bot_username: Optional[str] = None
    # Максимальный "возраст" данных входа от Telegram (защита от повторного
    # использования), по умолчанию 24 часа.
    init_data_max_age_seconds: int = 86400

    # Папка для хранения загруженных фотографий объектов (внутри контейнера).
    # Монтируется на Docker-том, чтобы фото не пропадали между перезапусками.
    photos_dir: str = "/data/photos"

    # Публичный HTTPS-адрес приложения (тот же, что у туннеля ngrok). Нужен,
    # чтобы при «поделиться» Telegram мог забрать фото по абсолютной ссылке.
    public_base_url: str = "https://pagan-crawling-retiring.ngrok-free.dev"

    # За сколько дней до окончания подписки начинать предупреждать владельца
    # агентства (бот пишет ему заранее). 0 — отключить предупреждения.
    subscription_warn_days: int = 3

    # Слать ли суперадмину уведомление в бот о непредвиденных сбоях сервера
    # (ошибки 500). По умолчанию включено; работает, только если задан BOT_TOKEN
    # и SUPERADMIN_TELEGRAM_ID.
    error_alerts_enabled: bool = True

    @field_validator("bot_token", "jwt_secret", "bot_username", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value):
        # Пустая строка в .env (например BOT_TOKEN=) трактуется как "не задано".
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("superadmin_telegram_id", mode="before")
    @classmethod
    def _empty_int_to_none(cls, value):
        # Пустую строку для числового поля тоже считаем "не задано",
        # иначе запуск упал бы с ошибкой парсинга.
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return None
        return value


settings = Settings()
