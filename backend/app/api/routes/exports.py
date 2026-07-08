"""
Экспорт базы объектов в файл — Этап 2.1.

ВАЖНО (грабли Telegram Mini App): скачивать файл «изнутри» приложения нельзя —
встроенный webview уходит на blob-страницу и зависает (чёрный экран). Поэтому
схема такая:
  1) приложение (с токеном) просит короткую ссылку — POST /exports/excel/link;
  2) открывает её во ВНЕШНЕМ браузере через Telegram.WebApp.openLink();
  3) внешний браузер качает файл по публичной ссылке /exports/excel/file?t=<jwt>.

Публичная ссылка содержит ОДНОРАЗОВЫЙ короткоживущий код (не токен доступа):
он живёт несколько минут, срабатывает один раз и сам по себе ничего не несёт —
просто ключ к серверной записи с id агентства. Поэтому утечка ссылки в логи/
историю после скачивания бесполезна.
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.core import download_tokens
from app.core.dependencies import require_agency_owner
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.db.models.user import User
from app.db.session import get_db
from app.services import excel_export_service

router = APIRouter(prefix="/exports", tags=["exports"])

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post(
    "/excel/link",
    dependencies=[Depends(rate_limit(10, 60, "export_excel_link"))],
)
def excel_link(
    current_user: User = Depends(require_agency_owner),
):
    """Вернуть короткую ссылку для скачивания .xlsx во внешнем браузере."""
    code = download_tokens.issue(current_user.agency_id)
    base = settings.public_base_url.rstrip("/")
    return {"url": f"{base}/api/v1/exports/excel/file?t={code}"}


@router.get(
    "/excel/file",
    include_in_schema=False,
    dependencies=[Depends(rate_limit(30, 60, "export_excel_file"))],
)
def excel_file(
    t: str = Query(default=""),
    db: Session = Depends(get_db),
):
    """Публичная отдача файла по одноразовому коду (открывается внешним браузером)."""
    agency_id = download_tokens.consume(t or "")
    if agency_id is None:
        raise AppError("export_link_invalid", status.HTTP_400_BAD_REQUEST)
    data = excel_export_service.build_xlsx(db, agency_id)
    filename = "realty-base.xlsx"
    return Response(
        content=data,
        media_type=_XLSX_MIME,
        headers={
            "Content-Disposition": f"attachment; filename={filename}; "
            f"filename*=UTF-8''{quote(filename)}",
        },
        status_code=status.HTTP_200_OK,
    )
