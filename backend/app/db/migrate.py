"""
Применение миграций Alembic при старте приложения.

Зачем отдельный модуль: раньше схему создавал Base.metadata.create_all() плюс
набор «ручных» ALTER TABLE. Теперь единый источник правды — миграции Alembic.

Логика «бережного онбординга» уже существующей базы (чтобы НЕ потерять данные):

  1. Если в базе уже есть служебная таблица alembic_version — просто
     накатываем миграции до самой свежей (upgrade head).
  2. Если alembic_version нет, НО таблицы приложения уже существуют
     (база создавалась до внедрения Alembic) — помечаем её отправной
     ревизией (stamp 0001_baseline), НИЧЕГО не пересоздавая, и затем
     накатываем последующие миграции.
  3. Если база пустая — Alembic создаёт всю схему с нуля (upgrade head).
"""
import logging
import time
from pathlib import Path

from sqlalchemy import inspect

from alembic import command
from alembic.config import Config
from app.db.session import engine

logger = logging.getLogger("uvicorn.error")

# Отправная ревизия (полная текущая схема). См. alembic/versions/0001_baseline.py.
BASELINE_REVISION = "0001_baseline"
# Любая «рабочая» таблица, по наличию которой судим, что база не пустая.
SENTINEL_TABLE = "agencies"


def _alembic_config() -> Config:
    """Собрать конфиг Alembic с абсолютными путями (работает и в Docker, и локально)."""
    # __file__ = .../backend/app/db/migrate.py → parents[2] = .../backend
    backend_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    return cfg


def _run_once() -> None:
    cfg = _alembic_config()
    existing_tables = set(inspect(engine).get_table_names())

    if "alembic_version" not in existing_tables and SENTINEL_TABLE in existing_tables:
        logger.info(
            "Обнаружена существующая база без истории миграций — "
            "помечаем её отправной ревизией %s (без пересоздания таблиц).",
            BASELINE_REVISION,
        )
        command.stamp(cfg, BASELINE_REVISION)

    command.upgrade(cfg, "head")
    logger.info("Миграции БД применены (схема обновлена до последней версии).")


def run_migrations(retries: int = 12, delay_seconds: int = 3) -> None:
    """Применить миграции, повторяя попытки, пока база не поднимется."""
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            _run_once()
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "Не удалось применить миграции (попытка %s/%s): %s",
                attempt, retries, exc,
            )
            time.sleep(delay_seconds)
    raise RuntimeError(f"Не удалось применить миграции БД: {last_error}")
