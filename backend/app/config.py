"""
Конфигурация backend. Все настройки читаются из переменных окружения
(или из файла .env). Это повторяет подход старого проекта: никаких секретов
в коде.

Сейчас (Часть 1A) обязательна только строка подключения к базе данных.
Поля bot_token и jwt_secret появятся на следующем шаге (Часть 1B) и пока
необязательны, чтобы проект запускался без токена бота.
"""
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Файл .env читается автоматически, если он есть рядом.
    # extra="ignore" — лишние переменные окружения не ломают запуск.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Подключение к PostgreSQL. По умолчанию — адрес базы внутри Docker,
    # где имя хоста "db" совпадает с именем сервиса в docker-compose.yml.
    database_url: str = "postgresql+psycopg://realty:realty_local_dev@db:5432/realty"

    # Понадобятся на следующем шаге (вход через Telegram). Пока необязательны.
    bot_token: Optional[str] = None
    jwt_secret: Optional[str] = None


# Единый экземпляр настроек, который импортируется по всему проекту.
settings = Settings()
