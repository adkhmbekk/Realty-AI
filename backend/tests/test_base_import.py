"""
Тесты импорта готовой базы клиента (.xlsx/.csv) — Этап 1.

Проверяем чистые функции (парсинг, эвристический маппинг, нормализацию значений)
и полный сценарий commit на SQLite в памяти (фикстура db из conftest).
ИИ-маппинг (Gemini) тут НЕ вызывается: без ключа suggest_mapping падает на
эвристику по названиям колонок.
"""
import io

from openpyxl import Workbook

from app.db.models.agency import Agency
from app.repositories import apartment_repo, user_repo
from app.services import base_import_service as bi


def _xlsx(rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_csv_and_xlsx_equivalent():
    header = ["Наименование", "Цена объекта", "Кол-во комнат"]
    rows = [header, ["Квартира центр", "55000", "3"], ["Дом", "120000", "5"]]
    csv_bytes = ("\n".join(";".join(r) for r in rows)).encode("utf-8")

    h_csv, d_csv = bi.parse_file("base.csv", csv_bytes)
    h_xlsx, d_xlsx = bi.parse_file("base.xlsx", _xlsx(rows))

    assert h_csv == header and h_xlsx == header
    assert d_csv[0][0] == "Квартира центр" and d_xlsx[0][0] == "Квартира центр"
    assert len(d_csv) == 2 and len(d_xlsx) == 2


def test_parse_xlsx_numeric_cells():
    # У клиента в Excel цена/комнаты — настоящие ЧИСЛА, а не текст. Раньше это
    # роняло парсинг ('int' object has no attribute 'strip'). Регрессия.
    rows = [["Наименование", "Цена", "Кол-во комнат", "Площадь"],
            ["Квартира центр", 55000, 3, 64.5],
            ["Дом", 120000, 5, 180]]
    header, data = bi.parse_file("base.xlsx", _xlsx(rows))
    assert header == ["Наименование", "Цена", "Кол-во комнат", "Площадь"]
    assert data[0] == ["Квартира центр", "55000", "3", "64.5"]
    # 180 — целое float из xlsx → "180", без ".0".
    assert data[1] == ["Дом", "120000", "5", "180"]


def test_heuristic_mapping_by_header_names():
    header = ["Наименование", "Район", "Цена", "Кол-во комнат", "Телефон собственника"]
    m = bi._heuristic_mapping(header)
    assert m["name"] == 0
    assert m["district"] == 1
    assert m["price"] == 2
    assert m["rooms"] == 3
    assert m["owner_phone"] == 4


def test_coerce_values():
    assert bi._coerce("price", "55 000") == 55000.0
    assert bi._coerce("rooms", "3 комн") == 3
    assert bi._coerce("currency", "у.е.") == "USD"
    assert bi._coerce("currency", "сум") == "UZS"
    assert bi._coerce("type", "2-комн квартира") == "Квартира"
    assert bi._coerce("furniture_appliances", "мебель и техника") == "furniture_and_appliances"
    assert bi._coerce("status", "Продан") == "sold"
    assert bi._coerce("name", "  Дом у реки ") == "Дом у реки"
    assert bi._coerce("price", "-5") is None


def test_build_payload_land_consistency():
    # type=Участок → этажи убираются, остаются сотки.
    header = ["Тип", "Соток", "Этаж"]
    mapping = {"type": 0, "land_area": 1, "floor": 2}
    body = bi._build_payload({**{f: None for f in bi.TARGET_CODES}, **mapping}, ["Участок", "8", "2"])
    assert body["type"] == "Участок"
    assert body["land_area"] == 8.0
    assert "floor" not in body


def _setup(db):
    agency = Agency(name="A", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(agency)
    db.flush()
    owner = user_repo.create(db, telegram_id=1, role="agency_admin", agency_id=agency.id, is_owner=True)
    db.commit()
    return agency.id, owner.id


def test_commit_creates_apartments(db):
    aid, uid = _setup(db)
    rows = [
        ["Наименование", "Цена", "Валюта", "Кол-во комнат"],
        ["Квартира 1", "50000", "USD", "2"],
        ["Квартира 2", "80000", "$", "3"],
        ["", "", "", ""],  # пустая строка — пропускается на парсинге
    ]
    content = _xlsx(rows)
    mapping = {"name": 0, "price": 1, "currency": 2, "rooms": 3}

    res = bi.commit(db, aid, created_by=uid, filename="base.xlsx", content=content, mapping=mapping)
    assert res["created"] == 2

    items, total = apartment_repo.search(db, aid, status=None)
    assert total == 2
    by_name = {a.name: a for a in items}
    assert float(by_name["Квартира 1"].price) == 50000.0
    assert by_name["Квартира 2"].currency == "USD"
    assert by_name["Квартира 2"].rooms == 3
