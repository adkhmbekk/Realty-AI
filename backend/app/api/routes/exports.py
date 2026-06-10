"""
Экспорт базы объектов в файл — Этап 2.1.

- excel: скачать все объекты агентства одним файлом .xlsx (односторонняя
  выгрузка, без подключения к Google). Доступ — главный администратор агентства.
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_owner
from app.core.ratelimit import rate_limit
from app.db.models.user import User
from app.db.session import get_db
from app.services import excel_export_service

router = APIRouter(prefix="/exports", tags=["exports"])

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/excel",
    dependencies=[Depends(rate_limit(10, 60, "export_excel"))],
)
def export_excel(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_owner),
):
    """Скачать все объекты агентства файлом .xlsx."""
    data = excel_export_service.build_xlsx(db, current_user.agency_id)
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
