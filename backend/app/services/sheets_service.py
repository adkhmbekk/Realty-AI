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
from datetime import datetime, timezone
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
from app.repositories import apartment_photo_repo, apartment_repo, user_repo
from app.schemas.apartment import ApartmentCreate, ApartmentUpdate
from app.services import apartment_service, dictionary_service, telegram_service
from app.services.listing_import_service import (
    CURRENCIES,
    OBJ_COND_VALUES,
    OBJ_TYPE_VALUES,
)

logger = logging.getLogger("uvicorn.error")

# Защита от случайного массового удаления через таблицу: если за один цикл из
# таблицы «исчезло» не меньше _DELETE_GUARD_MIN строк И это не меньше половины
# базы — удаление НЕ выполняем, строки возвращаем в таблицу и предупреждаем
# владельца. Так fat-finger («удалил все строки») не уносит данные.
_DELETE_GUARD_MIN = 5


def _is_mass_deletion(deleted: int, total: int) -> bool:
    if deleted < _DELETE_GUARD_MIN:
        return False
    if total <= 0:
        return True
    return deleted >= total * 0.5


def _notify_mass_deletion_blocked(db: Session, agency_id: int, count: int) -> None:
    """Best-effort: предупредить владельца агентства в бот об отменённом удалении."""
    try:
        if not telegram_service.is_configured():
            return
        owner = next(
            (u for u in user_repo.get_by_agency(db, agency_id)
             if u.role == "agency_admin" and u.is_owner and u.is_active),
            None,
        )
        if owner is None:
            return
        telegram_service.notify_async(
            [owner.telegram_id],
            "⚠️ Синхронизация Google-таблицы хотела удалить "
            f"{count} объектов — это похоже на случайное удаление строк. "
            "Удаление отменено, строки возвращены в таблицу. Если вы правда "
            "хотите удалить объекты — удаляйте по несколько за раз или в приложении.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("Sheets: не удалось предупредить об отменённом удалении: %s", exc)

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
_DRIVE_FILE_URL = "https://www.googleapis.com/drive/v3/files"
_TAB = "Объекты"          # имя листа с объектами
_MAX_ROWS = 5000

# Поля, участвующие в двусторонней синхронизации (канонические имена/коды).
# display_id — только для чтения; photo_urls/updated_at — служебные (не тянем назад).
SYNC_FIELDS = [
    "status", "name", "type", "district", "address", "rooms", "floor",
    "total_floors", "land_area", "area", "price", "currency", "condition",
    "furniture_appliances", "owner_phone", "description", "comment", "source_link",
]
_INT_FIELDS = {"rooms", "floor", "total_floors"}
_FLOAT_FIELDS = {"land_area", "area", "price"}
_ENUM_OK = {
    "type": set(OBJ_TYPE_VALUES),
    "condition": set(OBJ_COND_VALUES),
    "currency": set(CURRENCIES),
    "status": {"active", "deposit", "sold"},
    "furniture_appliances": {"furniture_and_appliances", "furniture_only", "appliances_only", "none"},
}
# Маркер «в ячейке мусор» (например, буквы в числовом поле) — такое поле не тянем.
_INVALID = object()


# ── Колонки таблицы (порядок = порядок столбцов) ─────────────────────
def _columns(districts: List[str]) -> List[dict]:
    """Описание колонок: заголовок, поле объекта, (необязательно) выпадающий список."""
    return [
        {"h": "ID", "f": "id"},
        {"h": "№", "f": "display_id", "w": 55},
        {"h": "Статус", "f": "status", "dd": list(STATUS_LABELS.values()), "w": 95},
        {"h": "Наименование", "f": "name", "w": 200},
        {"h": "Тип объекта", "f": "type", "dd": OBJ_TYPE_VALUES, "w": 115},
        {"h": "Район", "f": "district", "dd": districts, "w": 120},
        {"h": "Адрес", "f": "address", "w": 200},
        {"h": "Комнат", "f": "rooms", "w": 70},
        {"h": "Этаж", "f": "floor", "w": 60},
        {"h": "Этажей", "f": "total_floors", "w": 70},
        {"h": "Соток", "f": "land_area", "w": 70},
        {"h": "Площадь, м²", "f": "area", "w": 90},
        {"h": "Цена", "f": "price", "w": 100},
        {"h": "Валюта", "f": "currency", "dd": CURRENCIES, "w": 80},
        {"h": "Состояние", "f": "condition", "dd": OBJ_COND_VALUES, "w": 130},
        {"h": "Мебель/техника", "f": "furniture_appliances", "dd": list(FA_LABELS.values()), "w": 150},
        {"h": "Телефон собственника", "f": "owner_phone", "w": 150},
        {"h": "Описание", "f": "description", "w": 260},
        {"h": "Комментарий", "f": "comment", "w": 200},
        {"h": "Ссылка-источник", "f": "source_link", "w": 160},
        {"h": "Фото", "f": "photo_urls", "w": 160},
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


def _first_sheet_id(token: str, spreadsheet_id: str) -> int | None:
    """sheetId первого листа существующей таблицы (для переприменения оформления)."""
    data = _grequest(
        "GET", f"{_SHEETS_URL}/{spreadsheet_id}", token,
        params={"fields": "sheets.properties.sheetId"},
    )
    sheets = data.get("sheets") or []
    if not sheets:
        return None
    return sheets[0]["properties"]["sheetId"]


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


def export_matrix(db: Session, agency_id: int) -> tuple[List[dict], List[list]]:
    """(описание колонок, значения header+строки) для выгрузки в файл (Excel)."""
    districts = [
        d.value for d in dictionary_service.list_dictionaries(db, agency_id, category="district")
    ]
    cols = _columns(districts)
    return cols, _build_values(db, agency_id, cols)


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
    row.snapshot = _snapshot_now(db, agency_id)
    db.commit()
    return spreadsheet_url


def _apply_formatting(
    token: str, spreadsheet_id: str, sheet_id: int, cols: List[dict],
    with_protection: bool = True,
) -> None:
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
    # Защита шапки и колонки ID (предупреждение при правке). При повторном
    # применении к существующей таблице пропускаем, чтобы не плодить дубли.
    if with_protection:
      reqs.append({"addProtectedRange": {"protectedRange": {
        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
        "description": "Шапка — не редактировать", "warningOnly": True,
      }}})
      reqs.append({"addProtectedRange": {"protectedRange": {
        "range": {"sheetId": sheet_id, "startColumnIndex": 0, "endColumnIndex": 1},
        "description": "Технический ID — не редактировать", "warningOnly": True,
      }}})
    # Ширина колонок — чтобы короткие значения не висели в гигантских ячейках.
    for idx, c in enumerate(cols):
        w = c.get("w")
        if w:
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": idx, "endIndex": idx + 1},
                "properties": {"pixelSize": w}, "fields": "pixelSize",
            }})
    # Длинный текст (описание, список фото) обрезаем по ячейке, а не растягиваем
    # строку: полное значение видно при клике/в строке формул. Текст — по центру.
    reqs.append({"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": _MAX_ROWS},
        "cell": {"userEnteredFormat": {"wrapStrategy": "CLIP", "verticalAlignment": "MIDDLE"}},
        "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment",
    }})
    # Компактная фиксированная высота строк данных — таблица выглядит аккуратно.
    reqs.append({"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 1, "endIndex": _MAX_ROWS},
        "properties": {"pixelSize": 24}, "fields": "pixelSize",
    }})
    # Закрепить шапку, чтобы не терялась при прокрутке.
    reqs.append({"updateSheetProperties": {
        "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
        "fields": "gridProperties.frozenRowCount",
    }})
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
    # Переприменяем оформление (ширины, высоты, обрезку) — чтобы починить и
    # уже существующие таблицы, созданные до этого улучшения.
    sheet_id = _first_sheet_id(token, row.spreadsheet_id)
    if sheet_id is not None:
        _apply_formatting(token, row.spreadsheet_id, sheet_id, cols, with_protection=False)
    row.snapshot = _snapshot_now(db, agency_id)
    db.commit()
    return row.spreadsheet_url or ""


# ── Двусторонняя синхронизация (Этап 3) ──────────────────────────────
def _snapshot_now(db: Session, agency_id: int) -> dict:
    """Снимок текущего состояния БД: {"<id>": {field: value}} для merge."""
    items, _ = apartment_repo.search(db, agency_id, status=None, archived=False, limit=_MAX_ROWS)
    return {str(a.id): _canonical_jsonable(a) for a in items}
def _header_field_map() -> dict:
    """{заголовок столбца -> поле объекта} — для сопоставления колонок при чтении."""
    return {c["h"]: c["f"] for c in _columns([])}


def _norm(field: str, v) -> object:
    """Привести значение поля к сравнимому каноническому виду (или _INVALID)."""
    if v is None or v == "":
        return None
    if field in _INT_FIELDS:
        try:
            return int(float(str(v).replace(" ", "").replace(",", ".")))
        except (ValueError, TypeError):
            return _INVALID
    if field in _FLOAT_FIELDS:
        try:
            return round(float(str(v).replace(" ", "").replace(",", ".")), 2)
        except (ValueError, TypeError):
            return _INVALID
    return str(v).strip() or None


def _canonical(apt) -> dict:
    """Канонические значения синхронизируемых полей объекта из БД."""
    out = {}
    for f in SYNC_FIELDS:
        out[f] = _norm(f, getattr(apt, f, None))
    return out


def _parse_row(row_vals: List, header_to_field: dict) -> dict:
    """Из строки таблицы извлечь канонические значения синхронизируемых полей."""
    def at(field):
        idx = header_to_field.get(field)
        if idx is None or idx >= len(row_vals):
            return ""
        return row_vals[idx]

    out = {}
    for f in SYNC_FIELDS:
        raw = at(f)
        if f == "status":
            out[f] = _norm(f, STATUS_BY_LABEL.get(str(raw).strip(), ""))
        elif f == "furniture_appliances":
            out[f] = _norm(f, FA_BY_LABEL.get(str(raw).strip(), ""))
        else:
            out[f] = _norm(f, raw)
    return out


def _read_sheet(token: str, spreadsheet_id: str) -> List[List]:
    data = _grequest(
        "GET", f"{_SHEETS_URL}/{spreadsheet_id}/values/{quote(_TAB)}", token,
        params={"majorDimension": "ROWS"},
    )
    return data.get("values", []) or []


def _drive_modified_time(token: str, spreadsheet_id: str) -> Optional[datetime]:
    try:
        data = _grequest(
            "GET", f"{_DRIVE_FILE_URL}/{spreadsheet_id}", token,
            params={"fields": "modifiedTime"},
        )
        mt = data.get("modifiedTime")
        if mt:
            return datetime.fromisoformat(mt.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        pass
    return None


def _as_utc(dt) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _update_payload(changes: dict) -> dict:
    """Отфильтровать enum-поля по белым спискам (мусор не применяем)."""
    out = {}
    for f, v in changes.items():
        ok = _ENUM_OK.get(f)
        if ok is not None and v is not None and v not in ok:
            continue
        out[f] = v
    return out


def sync_agency(db: Session, agency_id: int) -> dict:
    """
    Один цикл двусторонней синхронизации для агентства.

    1) читаем таблицу и сравниваем со снимком → правки со стороны таблицы;
    2) применяем их в БД (с LWW для конфликтов: побеждает более позднее изменение);
    3) новые строки → создаём объекты; удалённые строки → в архив;
    4) перезаписываем таблицу из БД (пушим правки бота, проставляем ID);
    5) обновляем снимок.
    """
    row = db.get(AgencySheet, agency_id)
    if row is None or not row.refresh_token or not row.spreadsheet_id:
        return {"skipped": True}

    token = _access_token(row.refresh_token)
    sheet_mtime = _drive_modified_time(token, row.spreadsheet_id)
    grid = _read_sheet(token, row.spreadsheet_id)

    hf = {}
    if grid:
        hmap = _header_field_map()
        for i, h in enumerate(grid[0]):
            f = hmap.get(str(h).strip())
            if f:
                hf[f] = i

    id_idx = hf.get("id")
    sheet_by_id: dict = {}
    new_rows: List[dict] = []
    for r in grid[1:]:
        sid_raw = r[id_idx] if (id_idx is not None and id_idx < len(r)) else ""
        vals = _parse_row(r, hf)
        sid = None
        try:
            sid = int(str(sid_raw).strip()) if str(sid_raw).strip() else None
        except ValueError:
            sid = None
        if sid is not None:
            sheet_by_id[sid] = vals
        elif any(v not in (None, _INVALID) for v in vals.values()):
            new_rows.append(vals)

    snapshot = row.snapshot or {}
    items, _ = apartment_repo.search(db, agency_id, status=None, archived=False, limit=_MAX_ROWS)
    db_by_id = {a.id: a for a in items}

    pulled = created = archived = conflicts = 0

    # 1. Таблица → БД (с LWW).
    for aid, s_vals in sheet_by_id.items():
        apt = db_by_id.get(aid)
        if apt is None:
            continue
        snap = snapshot.get(str(aid), {})
        d_vals = _canonical(apt)
        changes: dict = {}
        status_to: Optional[str] = None
        for f in SYNC_FIELDS:
            s = s_vals.get(f)
            if s is _INVALID:
                continue
            p = snap.get(f)
            if not _diff(s, p):
                continue  # таблица это поле не меняла
            d = d_vals.get(f)
            if _diff(d, p):  # изменили обе стороны → конфликт, решаем по времени
                conflicts += 1
                d_time = _as_utc(apt.updated_at)
                if not (sheet_mtime and d_time and sheet_mtime > d_time):
                    continue  # БД новее или не определить — оставляем БД
            if f == "status":
                status_to = s
            else:
                changes[f] = s
        applied = _update_payload(changes)
        if applied:
            apartment_service.update_apartment(
                db, agency_id, aid, ApartmentUpdate(**applied), actor_id=None
            )
            pulled += 1
        if status_to and status_to in _ENUM_OK["status"] and status_to != apt.status:
            apartment_service.set_status(db, agency_id, aid, status_to, actor_id=None)
            pulled += 1

    # 2. Новые строки → создаём объекты.
    for vals in new_rows:
        body = {f: v for f, v in _update_payload(vals).items() if v not in (None, _INVALID)}
        if not body:
            continue
        try:
            apartment_service.create_apartment(
                db, agency_id, created_by=None, payload=ApartmentCreate(**body)
            )
            created += 1
        except AppError:
            continue

    # 3. Строки, что были в снимке, но исчезли из таблицы → в архив.
    # ЗАЩИТА: если удалений подозрительно много (см. _is_mass_deletion) — НЕ
    # удаляем, а вернём строки в таблицу (needs_write ниже) и предупредим владельца.
    sheet_ids = set(sheet_by_id.keys())
    to_delete: List[int] = []
    for sid_str in list(snapshot.keys()):
        try:
            aid = int(sid_str)
        except ValueError:
            continue
        if aid not in sheet_ids and aid in db_by_id:
            to_delete.append(aid)

    restored_deletion = False
    if to_delete and _is_mass_deletion(len(to_delete), len(db_by_id)):
        restored_deletion = True
        logger.warning(
            "Sheets: отменено массовое удаление %s из %s объектов (агентство %s) — "
            "строки вернутся в таблицу.", len(to_delete), len(db_by_id), agency_id,
        )
        _notify_mass_deletion_blocked(db, agency_id, len(to_delete))
    else:
        for aid in to_delete:
            apartment_service.delete_apartment(db, agency_id, aid)
            archived += 1

    # 4. Нужно ли что-то писать в таблицу? Пишем ТОЛЬКО при изменениях со стороны
    # бота (новые/архив/правки в БД, которых ещё нет в таблице). Иначе таблицу не
    # трогаем — так не затираем правки человека и сохраняем смысл modifiedTime.
    # restored_deletion → нужно вернуть «удалённые» строки обратно в таблицу.
    needs_write = created > 0 or archived > 0 or restored_deletion
    if not needs_write:
        for aid, apt in db_by_id.items():
            can = _canonical(apt)
            s_vals = sheet_by_id.get(aid)
            if s_vals is None:
                if str(aid) not in snapshot:  # новый объект из бота → дописать строку
                    needs_write = True
                    break
                continue
            if any(_diff(can.get(f), s_vals.get(f)) for f in SYNC_FIELDS):
                needs_write = True
                break

    if needs_write:
        districts = [
            d.value for d in dictionary_service.list_dictionaries(db, agency_id, category="district")
        ]
        cols = _columns(districts)
        _write_values(token, row.spreadsheet_id, _build_values(db, agency_id, cols))

    row.snapshot = _snapshot_now(db, agency_id)
    row.last_sync_at = datetime.now(timezone.utc)
    row.status = "connected"
    row.error_note = None
    db.commit()
    return {"pulled": pulled, "created": created, "archived": archived, "conflicts": conflicts}


def _diff(a, b) -> bool:
    """Разные ли значения (None/_INVALID учитываются как 'нет значения')."""
    a = None if a is _INVALID else a
    b = None if b is _INVALID else b
    return a != b


def _canonical_jsonable(apt) -> dict:
    """Снимок для JSON: _INVALID не попадёт (в БД его не бывает)."""
    return {f: (None if v is _INVALID else v) for f, v in _canonical(apt).items()}


def sync_all_connected(db: Session) -> int:
    """Прогнать цикл для всех агентств с подключённой таблицей (для планировщика)."""
    rows = db.query(AgencySheet).filter(
        AgencySheet.refresh_token.isnot(None),
        AgencySheet.spreadsheet_id.isnot(None),
    ).all()
    done = 0
    for r in rows:
        try:
            sync_agency(db, r.agency_id)
            done += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sheets sync agency %s: %s", r.agency_id, exc)
            try:
                r.status = "error"
                r.error_note = str(exc)[:200]
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
    return done
