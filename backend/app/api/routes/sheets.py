"""
Эндпоинты синхронизации с Google Sheets (Этап 2).

- connect: вернуть ссылку на согласие Google (открыть во внешнем браузере);
- oauth/callback: публичный — сюда Google возвращает код после согласия;
- status: подключено ли, есть ли таблица;
- create: создать таблицу и выгрузить объекты;
- export: перевыгрузить объекты в существующую таблицу;
- disconnect: отключить.

Управление подключением — только у главного администратора агентства.
"""
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_member, require_agency_owner
from app.core.ratelimit import rate_limit
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.sheet import SheetConnectOut, SheetCreateIn, SheetStatusOut
from app.services import sheets_service

router = APIRouter(prefix="/sheets", tags=["sheets"])


def _result_page(title: str, message: str, ok: bool) -> HTMLResponse:
    color = "#16a34a" if ok else "#dc2626"
    html = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head>
<body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#f4f6fb;
margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center">
<div style="background:#fff;border-radius:16px;padding:28px 24px;max-width:420px;
box-shadow:0 10px 30px rgba(0,0,0,.08);text-align:center">
<div style="font-size:40px;margin-bottom:8px">{'✅' if ok else '⚠️'}</div>
<h2 style="color:{color};margin:0 0 8px">{title}</h2>
<p style="color:#475569;margin:0 0 4px">{message}</p>
<p style="color:#94a3b8;font-size:13px;margin-top:14px">Можно вернуться в приложение Telegram.</p>
</div></body></html>"""
    return HTMLResponse(content=html)


@router.post("/connect", response_model=SheetConnectOut)
def connect(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_owner),
):
    """Вернуть ссылку на экран согласия Google (открывается во внешнем браузере)."""
    return {"auth_url": sheets_service.build_auth_url(current_user.agency_id)}


@router.get("/oauth/callback", include_in_schema=False)
def oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    db: Session = Depends(get_db),
):
    """Публичный колбэк Google: обмен кода на доступ. Возвращает HTML-страницу."""
    if error or not code:
        return _result_page("Доступ не выдан", "Подключение отменено. Попробуйте ещё раз.", False)
    try:
        sheets_service.exchange_code(db, code, state)
    except Exception:  # noqa: BLE001
        return _result_page("Не удалось подключить", "Повторите попытку и подтвердите доступ.", False)
    return _result_page("Google подключён", "Вернитесь в приложение и создайте таблицу.", True)


@router.get("/status", response_model=SheetStatusOut)
def get_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Статус подключения Google-таблицы для агентства."""
    return sheets_service.get_status(db, current_user.agency_id)


@router.post(
    "/create",
    dependencies=[Depends(rate_limit(5, 60, "sheets_create"))],
)
def create_sheet(
    body: SheetCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_owner),
):
    """Создать таблицу с выпадающими списками и выгрузить текущие объекты."""
    url = sheets_service.create_spreadsheet(db, current_user.agency_id, body.title)
    return {"spreadsheet_url": url}


@router.post(
    "/export",
    dependencies=[Depends(rate_limit(10, 60, "sheets_export"))],
)
def export_sheet(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_owner),
):
    """Перевыгрузить все объекты в уже созданную таблицу."""
    url = sheets_service.export_now(db, current_user.agency_id)
    return {"spreadsheet_url": url}


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_sheet(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_owner),
):
    """Отключить Google-таблицу от агентства."""
    sheets_service.disconnect(db, current_user.agency_id)
