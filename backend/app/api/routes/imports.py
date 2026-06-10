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
from app.schemas.base_import import BaseImportAnalyzeOut, BaseImportCommitOut
from app.services import base_import_service

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
