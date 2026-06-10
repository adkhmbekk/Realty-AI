"""
Экспорт базы объектов в файл — Этап 2.1.

ВАЖНО (грабли Telegram Mini App): скачивать файл «изнутри» приложения нельзя —
встроенный webview уходит на blob-страницу и зависает (чёрный экран). Поэтому
схема такая:
  1) приложение (с токеном) просит короткую ссылку — POST /exports/excel/link;
  2) открывает её во ВНЕШНЕМ браузере через Telegram.WebApp.openLink();
  3) внешний браузер качает файл по публичной ссылке /exports/excel/file?t=<jwt>.

Публичная ссылка защищена коротким подписанным токеном (внутри — id агентства),
поэтому без авторизационного заголовка скачать чужую базу нельзя.
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.core import security
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
    token = security.create_access_token({"dl_agency": current_user.agency_id})
    base = settings.public_base_url.rstrip("/")
    return {"url": f"{base}/api/v1/exports/excel/file?t={token}"}


@router.get("/excel/file", include_in_schema=False)
def excel_file(
    t: str = Query(default=""),
    db: Session = Depends(get_db),
):
    """Публичная отдача файла по короткому токену (открывается внешним браузером)."""
    payload = security.decode_access_token(t or "")
    if not payload or "dl_agency" not in payload:
        raise AppError("export_link_invalid", status.HTTP_400_BAD_REQUEST)
    agency_id = int(payload["dl_agency"])
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
