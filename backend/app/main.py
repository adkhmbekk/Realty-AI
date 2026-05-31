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
from sqlalchemy import select, text
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


def ensure_schema_upgrades() -> None:
    """
    Лёгкие до-Alembic-миграции: добавляем недостающие колонки в существующие
    таблицы, чтобы create_all (который НЕ умеет ALTER) не ломался на уже
    созданной базе. Данные при этом не теряются.
    """
    statements = [
        "ALTER TABLE agencies ADD COLUMN IF NOT EXISTS project_name VARCHAR",
    ]
    try:
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
        logger.info("Схема БД проверена (недостающие колонки добавлены при необходимости).")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось выполнить до-миграции схемы: %s", exc)


def normalize_legacy_display_ids() -> None:
    """
    Привести старые номера объектов к единому виду «0001».

    Раньше display_id формировался с префиксом кода агента (например
    «OTH-0001»). Теперь номер сквозной и числовой. Здесь однократно чистим
    старые записи: из display_id берём только цифры и дополняем до 4 знаков.
    При конфликте (такой номер уже занят) сдвигаем на следующий свободный.
    """
    import re

    db = SessionLocal()
    try:
        from app.db.models.apartment import Apartment

        apartments = db.execute(select(Apartment)).scalars().all()
        # Группируем по агентству, чтобы номера были уникальны в его пределах.
        by_agency: dict[int, list] = {}
        for a in apartments:
            by_agency.setdefault(a.agency_id, []).append(a)

        changed = 0
        for agency_id, items in by_agency.items():
            used = set()
            # Сначала фиксируем уже корректные числовые номера.
            for a in items:
                if a.display_id and re.fullmatch(r"\d+", a.display_id):
                    used.add(a.display_id.zfill(4))
            # Затем чиним нечисловые (например «OTH-0001»).
            for a in items:
                if a.display_id and re.fullmatch(r"\d+", a.display_id):
                    continue
                digits = "".join(ch for ch in (a.display_id or "") if ch.isdigit())
                num = int(digits) if digits else 1
                candidate = f"{num:04d}"
                while candidate in used:
                    num += 1
                    candidate = f"{num:04d}"
                a.display_id = candidate
                used.add(candidate)
                changed += 1
        if changed:
            db.commit()
            logger.info("Нормализовано номеров объектов: %s.", changed)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось нормализовать номера объектов: %s", exc)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db_with_retry()
    ensure_schema_upgrades()
    normalize_legacy_display_ids()
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
