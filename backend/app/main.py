"""
Точка входа backend-приложения Realty SaaS.

Часть 1B: добавлен вход через Telegram, роли и управление агентствами.
  - при старте создаём таблицы и (если задан) суперадмина;
  - GET /        — главная;
  - GET /health  — проверка сервиса и базы;
  - /api/v1/...  — рабочее API (см. интерактивную документацию на /docs).
"""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.router import api_router
from app.config import settings
from app.db import models  # noqa: F401  — нужен, чтобы модели зарегистрировались
from app.db.migrate import run_migrations
from app.db.session import SessionLocal, get_db
from app.repositories import user_repo

logger = logging.getLogger("uvicorn.error")


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


def backfill_agency_owners() -> None:
    """
    Для каждого агентства гарантируем одного «главного» админа (is_owner).
    Если ни у одного администратора агентства флаг не выставлен — назначаем
    самого раннего по дате создания администратора. Нужно для агентств,
    созданных до появления иерархии админов.
    """
    db = SessionLocal()
    try:
        from app.db.models.agency import Agency
        from app.db.models.user import User

        agency_ids = db.execute(select(Agency.id)).scalars().all()
        changed = 0
        for agency_id in agency_ids:
            admins = list(
                db.execute(
                    select(User)
                    .where(User.agency_id == agency_id, User.role == "agency_admin")
                    .order_by(User.created_at, User.id)
                ).scalars().all()
            )
            if not admins:
                continue
            if any(a.is_owner for a in admins):
                continue
            admins[0].is_owner = True
            changed += 1
        if changed:
            db.commit()
            logger.info("Назначено главных админов для агентств: %s.", changed)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось назначить главных админов: %s", exc)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    normalize_legacy_display_ids()
    backfill_agency_owners()
    bootstrap_superadmin()
    # Папка для фотографий объектов (на Docker-томе).
    try:
        import os
        os.makedirs(settings.photos_dir, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось создать папку для фото (%s): %s", settings.photos_dir, exc)
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
