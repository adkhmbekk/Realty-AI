"""
Точка входа backend-приложения Realty SaaS.

Часть 1A: подключаем базу данных.
  - при старте сервиса создаём таблицы (с повторными попытками — на случай,
    если база ещё не успела подняться);
  - GET /        — главная, показывает, что сервис запущен;
  - GET /health  — проверка, в том числе доступности базы данных.
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import engine, get_db
from app.db import models  # noqa: F401  — нужен, чтобы модели зарегистрировались

logger = logging.getLogger("uvicorn.error")


def init_db_with_retry(retries: int = 12, delay_seconds: int = 3) -> None:
    """
    Создать таблицы в базе. База в Docker может подниматься чуть дольше backend,
    поэтому пробуем несколько раз, прежде чем сдаться.
    """
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
    # Если так и не получилось — падаем с понятной ошибкой.
    raise RuntimeError(f"Не удалось инициализировать базу данных: {last_error}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Код до yield выполняется один раз при запуске сервиса.
    init_db_with_retry()
    yield
    # Код после yield — при остановке (сейчас ничего не требуется).


app = FastAPI(
    title="Realty SaaS API",
    description="Backend для Telegram Mini App риелторских агентств",
    version="0.2.0",
    lifespan=lifespan,
)


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
