"""
Эндпоинты импорта готовой базы клиента из файла (.xlsx/.csv) — Этап 1.

- analyze: загрузить файл → вернуть колонки, образцы строк и предложенный
  (ИИ) маппинг колонок на наши поля. Ничего не сохраняет.
- commit:  загрузить файл повторно + подтверждённый маппинг → создать объекты.

Файл на сервере не хранится: на шаге commit он присылается заново вместе с
маппингом. Импорт доступен только главному администратору агентства.
"""
import json

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_owner
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.db.models.user import User
from app.db.session import get_db
from typing import List

from app.schemas.base_import import BaseImportAnalyzeOut, BaseImportCommitOut
from app.schemas.tg_import import TelegramScanIn, TelegramScanOut, WatchIn, WatchOut
from app.services import base_import_service, telegram_channel_service

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post(
    "/base/analyze",
    response_model=BaseImportAnalyzeOut,
    dependencies=[Depends(rate_limit(10, 60, "import_base_analyze"))],
)
async def analyze_base(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_owner),
):
    """Разобрать загруженный файл и предложить сопоставление колонок (ИИ)."""
    content = await file.read()
    return base_import_service.analyze(file.filename or "", content)


@router.post(
    "/base/commit",
    response_model=BaseImportCommitOut,
    dependencies=[Depends(rate_limit(5, 60, "import_base_commit"))],
)
async def commit_base(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_owner),
):
    """Создать объекты по подтверждённому маппингу колонок."""
    try:
        mapping_dict = json.loads(mapping or "{}")
        if not isinstance(mapping_dict, dict):
            raise ValueError
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppError("import_no_mapping", status.HTTP_400_BAD_REQUEST) from exc

    content = await file.read()
    return base_import_service.commit(
        db, current_user.agency_id, created_by=current_user.id,
        filename=file.filename or "", content=content, mapping=mapping_dict,
    )


@router.post(
    "/telegram/scan",
    response_model=TelegramScanOut,
    dependencies=[Depends(rate_limit(40, 60, "import_tg_scan"))],
)
async def scan_telegram(
    body: TelegramScanIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_owner),
):
    """Обработать одну страницу ленты открытого Telegram-канала (постранично)."""
    return await telegram_channel_service.scan_page(
        db, current_user.agency_id, current_user.id, body.channel, body.before, body.share_mls
    )


# ── Фоновое слежение за каналом (авто-импорт новых постов) ───────────────────
@router.get("/telegram/watches", response_model=List[WatchOut])
def list_watches(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_owner),
):
    """Список каналов, за которыми следит агентство (авто-импорт)."""
    return telegram_channel_service.list_watches(db, current_user.agency_id)


@router.post("/telegram/watches", response_model=WatchOut)
def add_watch(
    body: WatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_owner),
):
    """Включить слежение за каналом: новые посты будут добавляться автоматически."""
    return telegram_channel_service.add_watch(
        db, current_user.agency_id, current_user.id, body.channel, body.share_mls
    )


@router.delete("/telegram/watches/{watch_id}", status_code=204)
def remove_watch(
    watch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_owner),
):
    """Выключить слежение за каналом."""
    telegram_channel_service.remove_watch(db, current_user.agency_id, watch_id)
