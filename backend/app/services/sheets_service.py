"""
Синхронизация с Google Sheets — Этап 2 (подключение + выгрузка БД → таблица).

Подключение: OAuth 2.0. Платформа имеет ОДНО OAuth-приложение (client_id/secret).
Владелец агентства жмёт «Подключить», даёт согласие в Google → мы получаем
refresh-токен (доступ только к файлам, созданным приложением — скоуп drive.file).
Затем приложение само создаёт таблицу с нужными колонками, выпадающими списками
для enum-полей и выгружает текущие объекты.

Все вызовы Google — напрямую по REST через httpx (без сторонних SDK).

Этап 3 (обратная синхронизация + конфликты LWW) добавится поверх этого.
"""
import logging
from decimal import Decimal
from typing import List, Optional
from urllib.parse import quote, urlencode

import httpx
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.config import settings
from app.core import security
from app.core.errors import AppError
from app.db.models.agency_sheet import AgencySheet
from app.repositories import apartment_photo_repo, apartment_repo
from app.services import dictionary_service
from app.services.listing_import_service import (
    CURRENCIES,
    OBJ_COND_VALUES,
    OBJ_TYPE_VALUES,
)

logger = logging.getLogger("uvicorn.error")

# ── Подписи enum-значений в таблице (человекочитаемые) ───────────────
STATUS_LABELS = {"active": "Активен", "deposit": "Задаток", "sold": "Продан"}
STATUS_BY_LABEL = {v: k for k, v in STATUS_LABELS.items()}
FA_LABELS = {
    "furniture_and_appliances": "Мебель и техника",
    "furniture_only": "Только мебель",
    "appliances_only": "Только техника",
    "none": "Без мебели и техники",
}
FA_BY_LABEL = {v: k for k, v in FA_LABELS.items()}

# ── Google endpoints ─────────────────────────────────────────────────
_SCOPE = "https://www.googleapis.com/auth/drive.file"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_SHEETS_URL = "https://sheets.googleapis.com/v4/spreadsheets"
_TAB = "Объекты"          # имя листа с объектами
_MAX_ROWS = 5000


# ── Колонки таблицы (порядок = порядок столбцов) ─────────────────────
def _columns(districts: List[str]) -> List[dict]:
    """Описание колонок: заголовок, поле объекта, (необязательно) выпадающий список."""
    return [
        {"h": "ID", "f": "id"},
        {"h": "№", "f": "display_id"},
        {"h": "Статус", "f": "status", "dd": list(STATUS_LABELS.values())},
        {"h": "Наименование", "f": "name"},
        {"h": "Тип объекта", "f": "type", "dd": OBJ_TYPE_VALUES},
        {"h": "Район", "f": "district", "dd": districts},
        {"h": "Адрес", "f": "address"},
        {"h": "Комнат", "f": "rooms"},
        {"h": "Этаж", "f": "floor"},
        {"h": "Этажей", "f": "total_floors"},
        {"h": "Соток", "f": "land_area"},
        {"h": "Площадь, м²", "f": "area"},
        {"h": "Цена", "f": "price"},
        {"h": "Валюта", "f": "currency", "dd": CURRENCIES},
        {"h": "Состояние", "f": "condition", "dd": OBJ_COND_VALUES},
        {"h": "Мебель/техника", "f": "furniture_appliances", "dd": list(FA_LABELS.values())},
        {"h": "Телефон собственника", "f": "owner_phone"},
        {"h": "Описание", "f": "description"},
        {"h": "Комментарий", "f": "comment"},
        {"h": "Ссылка-источник", "f": "source_link"},
        {"h": "Фото", "f": "photo_urls"},
        {"h": "Изменено", "f": "updated_at"},
    ]


def _cell(field: str, apt, photos_map: dict) -> object:
    if field == "status":
        return STATUS_LABELS.get(apt.status, apt.status)
    if field == "furniture_appliances":
        return FA_LABELS.get(apt.furniture_appliances, "") if apt.furniture_appliances else ""
    if field == "photo_urls":
        base = settings.public_base_url.rstrip("/")
        return "\n".join(base + "/api/v1/photos/" + k for k in photos_map.get(apt.id, []))
    if field == "updated_at":
        return apt.updated_at.isoformat() if apt.updated_at else ""
    v = getattr(apt, field, None)
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return float(v)
    return v


# ── OAuth ─────────────────────────────────────────────────────────────
def _redirect_uri() -> str:
    return settings.public_base_url.rstrip("/") + "/api/v1/sheets/oauth/callback"


def build_auth_url(agency_id: int) -> str:
    """Ссылка на экран согласия Google для подключения таблицы."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise AppError("sheets_not_configured", http_status.HTTP_503_SERVICE_UNAVAILABLE)
    state = security.create_access_token({"so_agency": agency_id})
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": _SCOPE,
        "access_type": "offline",
        "prompt": "consent",          # всегда выдаёт refresh_token
        "include_granted_scopes": "true",
        "state": state,
    }
    return _AUTH_URL + "?" + urlencode(params)


def exchange_code(db: Session, code: str, state: str) -> int:
    """Обменять код авторизации на refresh-токен и сохранить его. Вернуть agency_id."""
    payload = security.decode_access_token(state or "")
    if not payload or "so_agency" not in payload:
        raise AppError("sheets_oauth_failed", http_status.HTTP_400_BAD_REQUEST)
    agency_id = int(payload["so_agency"])
    try:
        r = httpx.post(_TOKEN_URL, data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": _redirect_uri(),
        }, timeout=20)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sheets OAuth: сеть/обмен кода: %s", exc)
        raise AppError("sheets_oauth_failed", http_status.HTTP_400_BAD_REQUEST) from exc
    if r.status_code != 200:
        logger.warning("Sheets OAuth: обмен кода %s: %s", r.status_code, r.text[:300])
        raise AppError("sheets_oauth_failed", http_status.HTTP_400_BAD_REQUEST)
    refresh = r.json().get("refresh_token")
    if not refresh:
        raise AppError("sheets_oauth_failed", http_status.HTTP_400_BAD_REQUEST)

    row = _get_or_create(db, agency_id)
    row.refresh_token = refresh
    row.status = "connected"
    row.error_note = None
    db.commit()
    return agency_id


def _access_token(refresh_token: str) -> str:
    try:
        r = httpx.post(_TOKEN_URL, data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
        }, timeout=20)
        r.raise_for_status()
        return r.json()["access_token"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sheets: не удалось обновить access-токен: %s", exc)
        raise AppError("sheets_api_error", http_status.HTTP_502_BAD_GATEWAY) from exc


# ── Доступ к строке agency_sheets ────────────────────────────────────
def _get_or_create(db: Session, agency_id: int) -> AgencySheet:
    row = db.get(AgencySheet, agency_id)
    if row is None:
        row = AgencySheet(agency_id=agency_id, status="disconnected")
        db.add(row)
        db.flush()
    return row


def get_status(db: Session, agency_id: int) -> dict:
    row = db.get(AgencySheet, agency_id)
    if row is None:
        return {"connected": False, "status": "disconnected", "has_spreadsheet": False}
    return {
        "connected": bool(row.refresh_token),
        "status": row.status,
        "has_spreadsheet": bool(row.spreadsheet_id),
        "spreadsheet_url": row.spreadsheet_url,
        "sheet_title": row.sheet_title,
        "error_note": row.error_note,
    }


def disconnect(db: Session, agency_id: int) -> None:
    row = db.get(AgencySheet, agency_id)
    if row is None:
        return
    if row.refresh_token:
        try:
            httpx.post(_REVOKE_URL, params={"token": row.refresh_token}, timeout=10)
        except Exception:  # noqa: BLE001
            pass
    row.refresh_token = None
    row.spreadsheet_id = None
    row.spreadsheet_url = None
    row.status = "disconnected"
    row.error_note = None
    db.commit()


# ── Создание таблицы и выгрузка ──────────────────────────────────────
def _gpost(url: str, token: str, body: dict) -> dict:
    return _grequest("POST", url, token, json=body)


def _grequest(method: str, url: str, token: str, **kw) -> dict:
    try:
        r = httpx.request(method, url, headers={"Authorization": "Bearer " + token}, timeout=30, **kw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sheets API сеть: %s", exc)
        raise AppError("sheets_api_error", http_status.HTTP_502_BAD_GATEWAY) from exc
    if r.status_code >= 400:
        logger.warning("Sheets API %s %s: %s", method, r.status_code, r.text[:400])
        raise AppError("sheets_api_error", http_status.HTTP_502_BAD_GATEWAY)
    return r.json() if r.content else {}


def _build_values(db: Session, agency_id: int, cols: List[dict]) -> List[list]:
    items, _ = apartment_repo.search(
        db, agency_id, status=None, archived=False, limit=_MAX_ROWS, offset=0
    )
    photos_map = {
        a.id: [p.storage_key for p in apartment_photo_repo.list_for(db, agency_id, a.id)]
        for a in items
    }
    header = [c["h"] for c in cols]
    rows = [[_cell(c["f"], a, photos_map) for c in cols] for a in items]
    return [header] + rows


def _write_values(token: str, spreadsheet_id: str, values: List[list]) -> None:
    # Чистим лист и пишем заново (простой и надёжный экспорт на Этапе 2).
    _gpost(
        f"{_SHEETS_URL}/{spreadsheet_id}/values/{quote(_TAB)}:clear",
        token, {},
    )
    rng = quote(f"{_TAB}!A1")
    _grequest(
        "PUT", f"{_SHEETS_URL}/{spreadsheet_id}/values/{rng}",
        token, params={"valueInputOption": "RAW"}, json={"values": values},
    )


def create_spreadsheet(db: Session, agency_id: int, title: str) -> str:
    """Создать таблицу, оформить (списки, защита), выгрузить объекты. Вернуть URL."""
    row = db.get(AgencySheet, agency_id)
    if row is None or not row.refresh_token:
        raise AppError("sheets_not_connected", http_status.HTTP_400_BAD_REQUEST)

    token = _access_token(row.refresh_token)
    districts = [
        d.value for d in dictionary_service.list_dictionaries(db, agency_id, category="district")
    ]
    cols = _columns(districts)

    created = _gpost(_SHEETS_URL, token, {
        "properties": {"title": title},
        "sheets": [{"properties": {"title": _TAB, "gridProperties": {"frozenRowCount": 1}}}],
    })
    spreadsheet_id = created["spreadsheetId"]
    spreadsheet_url = created["spreadsheetUrl"]
    sheet_id = created["sheets"][0]["properties"]["sheetId"]

    _write_values(token, spreadsheet_id, _build_values(db, agency_id, cols))
    _apply_formatting(token, spreadsheet_id, sheet_id, cols)

    row.spreadsheet_id = spreadsheet_id
    row.spreadsheet_url = spreadsheet_url
    row.sheet_title = title
    row.status = "connected"
    row.error_note = None
    db.commit()
    return spreadsheet_url


def _apply_formatting(token: str, spreadsheet_id: str, sheet_id: int, cols: List[dict]) -> None:
    reqs: List[dict] = []
    # Жирная шапка.
    reqs.append({"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
        "fields": "userEnteredFormat.textFormat.bold",
    }})
    # Выпадающие списки для enum-колонок.
    for idx, c in enumerate(cols):
        dd = c.get("dd")
        if dd:
            reqs.append({"setDataValidation": {
                "range": {
                    "sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": _MAX_ROWS,
                    "startColumnIndex": idx, "endColumnIndex": idx + 1,
                },
                "rule": {
                    "condition": {"type": "ONE_OF_LIST",
                                  "values": [{"userEnteredValue": v} for v in dd]},
                    "strict": False, "showCustomUi": True,
                },
            }})
    # Защита шапки и колонки ID (предупреждение при правке).
    reqs.append({"addProtectedRange": {"protectedRange": {
        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
        "description": "Шапка — не редактировать", "warningOnly": True,
    }}})
    reqs.append({"addProtectedRange": {"protectedRange": {
        "range": {"sheetId": sheet_id, "startColumnIndex": 0, "endColumnIndex": 1},
        "description": "Технический ID — не редактировать", "warningOnly": True,
    }}})
    # Прячем служебные колонки: ID (0) и «Изменено» (последняя).
    for col_idx in (0, len(cols) - 1):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": col_idx, "endIndex": col_idx + 1},
            "properties": {"hiddenByUser": True}, "fields": "hiddenByUser",
        }})
    _gpost(f"{_SHEETS_URL}/{spreadsheet_id}:batchUpdate", token, {"requests": reqs})


def export_now(db: Session, agency_id: int) -> str:
    """Перевыгрузить все объекты в уже созданную таблицу (ручное обновление)."""
    row = db.get(AgencySheet, agency_id)
    if row is None or not row.refresh_token or not row.spreadsheet_id:
        raise AppError("sheets_not_connected", http_status.HTTP_400_BAD_REQUEST)
    token = _access_token(row.refresh_token)
    districts = [
        d.value for d in dictionary_service.list_dictionaries(db, agency_id, category="district")
    ]
    cols = _columns(districts)
    _write_values(token, row.spreadsheet_id, _build_values(db, agency_id, cols))
    db.commit()
    return row.spreadsheet_url or ""
