"""
Тесты менеджера дубликатов: нормализация телефона, группировка по номеру,
подтверждение «не дубликаты».
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


def _mk(db, aid, uid, phone, name):
    return apartment_service.create_apartment(
        db, aid, created_by=uid,
        payload=ApartmentCreate(name=name, owner_phone=phone, price=1000),
    )


def test_normalize_phone():
    assert dup.normalize_phone("+998 90 123 45 67") == "901234567"
    assert dup.normalize_phone("(90) 123-45-67") == "901234567"
    assert dup.normalize_phone("998901234567") == "901234567"
    assert dup.normalize_phone("123") is None
    assert dup.normalize_phone(None) is None


def test_groups_by_phone(db):
    aid, uid = _setup(db)
    _mk(db, aid, uid, "+998901112233", "A1")
    _mk(db, aid, uid, "998 90 111 22 33", "A2")  # тот же номер, другой формат
    _mk(db, aid, uid, "901112233", "A3")
    _mk(db, aid, uid, "+998907777777", "B1")  # одиночка — не группа

    groups = dup.find_duplicate_groups(db, aid)
    assert len(groups) == 1
    assert groups[0]["count"] == 3
    assert {i.name for i in groups[0]["items"]} == {"A1", "A2", "A3"}


def test_dismiss_hides_group(db):
    aid, uid = _setup(db)
    _mk(db, aid, uid, "901112233", "A1")
    _mk(db, aid, uid, "901112233", "A2")
    groups = dup.find_duplicate_groups(db, aid)
    assert len(groups) == 1
    key = groups[0]["key"]

    dup.dismiss_group(db, aid, key)
    assert dup.find_duplicate_groups(db, aid) == []


def test_deleted_not_grouped(db):
    aid, uid = _setup(db)
    a1 = _mk(db, aid, uid, "901112233", "A1")
    _mk(db, aid, uid, "901112233", "A2")
    # Архивируем один — остаётся один активный, группы больше нет.
    apartment_service.delete_apartment(db, aid, a1.id)
    assert dup.find_duplicate_groups(db, aid) == []
