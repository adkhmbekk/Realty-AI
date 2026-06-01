"""
Окружение Alembic.

Адрес базы берём из настроек приложения (app.config.settings.database_url),
а не из alembic.ini — чтобы был один источник правды и не дублировать секреты.
target_metadata = Base.metadata: импортируем все модели, чтобы автогенерация
видела полную схему.
"""
from sqlalchemy import engine_from_config, pool

from alembic import context

# Настройки приложения и метаданные всех таблиц.
from app.config import settings
from app.db import models  # noqa: F401  — импорт регистрирует все модели в Base.metadata
from app.db.base import Base

# Объект конфигурации Alembic (доступ к значениям из alembic.ini).
config = context.config

# Подставляем реальный адрес БД из настроек приложения.
# Экранируем «%», т.к. ConfigParser трактует его как спецсимвол интерполяции.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

# Намеренно НЕ вызываем fileConfig(): при запуске миграций из приложения
# это сбросило бы настройку логирования uvicorn. Логи о ходе миграций пишет
# app/db/migrate.py.

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Миграции в offline-режиме (генерация SQL без подключения к БД)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Миграции в online-режиме (с реальным подключением к БД)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
