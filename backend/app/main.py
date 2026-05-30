"""
Точка входа backend-приложения Realty SaaS.

Часть 1B: добавлен вход через Telegram, роли и управление агентствами.
  - при старте создаём таблицы и (если задан) суперадмина;
  - GET /        — главная;
  - GET /health  — проверка сервиса и базы;
  - /api/v1/...  — рабочее API (см. интерактивную документацию на /docs).
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.router import api_router
from app.config import settings
from app.db import models  # noqa: F401  — нужен, чтобы модели зарегистрировались
from app.db.base import Base
from app.db.session import SessionLocal, engine, get_db
from app.repositories import user_repo

logger = logging.getLogger("uvicorn.error")


def init_db_with_retry(retries: int = 12, delay_seconds: int = 3) -> None:
    """Создать таблицы, повторяя попытки, пока база не поднимется."""
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("База данных готова, таблицы созданы/проверены.")
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "Не удалось подключиться к базе (попытка %s/%s): %s",
                attempt, retries, exc,
            )
            time.sleep(delay_seconds)
    raise RuntimeError(f"Не удалось инициализировать базу данных: {last_error}")


def bootstrap_superadmin() -> None:
    """
    Если в настройках задан SUPERADMIN_TELEGRAM_ID — сделать этого человека
    суперадмином (создать или повысить). Так владелец платформы получает
    доступ без ручного редактирования базы.
    """
    if not settings.superadmin_telegram_id:
        logger.info("SUPERADMIN_TELEGRAM_ID не задан — суперадмин не создаётся.")
        return

    db = SessionLocal()
    try:
        existing = user_repo.get_by_telegram_id(db, settings.superadmin_telegram_id)
        if existing is None:
            user_repo.create(
                db,
                telegram_id=settings.superadmin_telegram_id,
                role="superadmin",
                agency_id=None,
            )
            logger.info("Создан суперадмин (telegram_id=%s).", settings.superadmin_telegram_id)
        elif existing.role != "superadmin":
            existing.role = "superadmin"
            existing.agency_id = None
            existing.is_active = True
            logger.info("Пользователь повышен до суперадмина.")
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db_with_retry()
    bootstrap_superadmin()
    yield


app = FastAPI(
    title="Realty SaaS API",
    description="Backend для Telegram Mini App риелторских агентств",
    version="0.3.0",
    lifespan=lifespan,
)

# Подключаем рабочее API под префиксом /api/v1.
app.include_router(api_router)


@app.get("/")
def root():
    """Главная страница. Если ты видишь это в браузере — backend работает."""
    return {
        "status": "ok",
        "service": "Realty SaaS backend",
        "message": "Поздравляю! Backend успешно запущен и работает.",
    }


@app.get("/health")
def health(db: Session = Depends(get_db)):
    """Проверка: жив ли сервис и доступна ли база данных."""
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "unavailable",
    }
