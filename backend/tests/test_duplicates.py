"""
Тесты менеджера дубликатов (v3): группировка по совпадению фиксированных
характеристик (район, комнаты, этаж, этажность, площадь, сотки); ТИП и ЦЕНА
не участвуют; минимум заполненности; подтверждение «не дубликаты».
"""
from app.db.models.agency import Agency
from app.repositories import user_repo
from app.schemas.apartment import ApartmentCreate
from app.services import apartment_service, duplicate_service as dup


def _setup(db):
    agency = Agency(name="A", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(agency)
    db.flush()
    owner = user_repo.create(db, telegram_id=1, role="agency_admin", agency_id=agency.id, is_owner=True)
    db.commit()
    return agency.id, owner.id


def _mk(db, aid, uid, name, **fields):
    return apartment_service.create_apartment(
        db, aid, created_by=uid,
        payload=ApartmentCreate(name=name, **fields),
    )


FLAT = dict(type="Квартира", district="Юнусабад", rooms=3, floor=5, total_floors=9, area=70)


def test_normalize_phone():
    assert dup.normalize_phone("+998 90 123 45 67") == "901234567"
    assert dup.normalize_phone("(90) 123-45-67") == "901234567"
    assert dup.normalize_phone("998901234567") == "901234567"
    assert dup.normalize_phone("123") is None
    assert dup.normalize_phone(None) is None


def test_groups_by_attributes_price_ignored(db):
    aid, uid = _setup(db)
    # Один объект из трёх источников: характеристики совпали, цены РАЗНЫЕ.
    _mk(db, aid, uid, "A1", **FLAT, price=50000)
    _mk(db, aid, uid, "A2", **FLAT, price=52000)
    _mk(db, aid, uid, "A3", **FLAT, price=49500)
    # Похожий, но другой объект (другая комнатность) — не в группе.
    _mk(db, aid, uid, "B1", **{**FLAT, "rooms": 2}, price=50000)

    groups = dup.find_duplicate_groups(db, aid)
    assert len(groups) == 1
    assert groups[0]["count"] == 3
    assert {i.name for i in groups[0]["items"]} == {"A1", "A2", "A3"}
    assert groups[0]["label"]  # человекочитаемое описание группы


def test_area_float_int_same_key(db):
    aid, uid = _setup(db)
    # 70 и 70.0 — одна площадь; регистр/пробелы района не важны.
    _mk(db, aid, uid, "A1", type="Квартира", district="Юнусабад", rooms=3, area=70)
    _mk(db, aid, uid, "A2", type="Квартира", district="  юнусабад ", rooms=3, area=70.0)
    groups = dup.find_duplicate_groups(db, aid)
    assert len(groups) == 1
    assert groups[0]["count"] == 2


def test_type_fully_ignored(db):
    aid, uid = _setup(db)
    # Один объект, который источники назвали по-разному: Дом / Участок / Земля.
    base = dict(district="Кибрай", rooms=4, total_floors=2, area=120, land_area=6)
    _mk(db, aid, uid, "H1", type="Дом", **base, price=80000)
    _mk(db, aid, uid, "H2", type="Участок", **base, price=85000)
    _mk(db, aid, uid, "H3", type="Земля", **base, price=78000)
    # Объект с другими числами (нет соток) — НЕ в группе: числа не совпали.
    _mk(db, aid, uid, "F1", type="Квартира", district="Кибрай", rooms=4, total_floors=2, area=120)

    groups = dup.find_duplicate_groups(db, aid)
    assert len(groups) == 1
    assert groups[0]["count"] == 3
    assert {i.name for i in groups[0]["items"]} == {"H1", "H2", "H3"}

    # А если совпали ВСЕ числа — группа образуется даже при «несовместимых» типах.
    _mk(db, aid, uid, "C1", type="Квартира", district="Чиланзар", rooms=2, floor=3, total_floors=5, area=48)
    _mk(db, aid, uid, "C2", type="Коммерция", district="Чиланзар", rooms=2, floor=3, total_floors=5, area=48)
    groups = dup.find_duplicate_groups(db, aid)
    assert len(groups) == 2


def test_same_price_also_grouped(db):
    aid, uid = _setup(db)
    # Цена не влияет: ОДИНАКОВЫЕ цены тоже показываются как дубликаты.
    _mk(db, aid, uid, "A1", **FLAT, price=50000)
    _mk(db, aid, uid, "A2", **FLAT, price=50000)
    groups = dup.find_duplicate_groups(db, aid)
    assert len(groups) == 1
    assert groups[0]["count"] == 2


def test_too_empty_not_grouped(db):
    aid, uid = _setup(db)
    # Заполнено меньше 3 характеристик — слишком пусто, чтобы судить о дублях.
    _mk(db, aid, uid, "A1", type="Квартира", rooms=3, price=1000)
    _mk(db, aid, uid, "A2", type="Квартира", rooms=3, price=2000)
    assert dup.find_duplicate_groups(db, aid) == []


def test_dismiss_hides_group(db):
    aid, uid = _setup(db)
    _mk(db, aid, uid, "A1", **FLAT)
    _mk(db, aid, uid, "A2", **FLAT)
    groups = dup.find_duplicate_groups(db, aid)
    assert len(groups) == 1
    key = groups[0]["key"]

    dup.dismiss_group(db, aid, key)
    assert dup.find_duplicate_groups(db, aid) == []


def test_deleted_not_grouped(db):
    aid, uid = _setup(db)
    a1 = _mk(db, aid, uid, "A1", **FLAT)
    _mk(db, aid, uid, "A2", **FLAT)
    # Архивируем один — остаётся один активный, группы больше нет.
    apartment_service.delete_apartment(db, aid, a1.id)
    assert dup.find_duplicate_groups(db, aid) == []
