"""added_via при создании объекта + просмотр объектов агентства владельцем платформы
(телефон собственника скрыт)."""
from app.db.models.agency import Agency
from app.repositories import user_repo
from app.schemas.apartment import ApartmentCreate
from app.services import agency_service, apartment_service


def _setup(db):
    ag = Agency(name="AO", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(ag)
    db.flush()
    u = user_repo.create(db, telegram_id=1, role="agency_admin", agency_id=ag.id, is_owner=True)
    db.commit()
    return ag, u


def test_added_via_classification(db):
    ag, u = _setup(db)
    a_manual = apartment_service.create_apartment(db, ag.id, u.id, ApartmentCreate(district="Ч", price=1000))
    a_link = apartment_service.create_apartment(db, ag.id, u.id, ApartmentCreate(district="Ч", price=1000, source="olx.uz"))
    a_bulk = apartment_service.create_apartment(db, ag.id, u.id, ApartmentCreate(district="Ч", price=1000, source="@ch"), "bulk")
    a_auto = apartment_service.create_apartment(db, ag.id, u.id, ApartmentCreate(district="Ч", price=1000, source="@ch2"), "auto")
    assert a_manual.added_via == "manual"   # вручную (нет источника)
    assert a_link.added_via == "link"       # импорт по ссылке (домен)
    assert a_bulk.added_via == "bulk"       # массовый импорт из канала
    assert a_auto.added_via == "auto"       # авто-импорт из канала


def test_list_objects_hides_owner_phone(db):
    ag, u = _setup(db)
    apartment_service.create_apartment(
        db, ag.id, u.id, ApartmentCreate(district="Ч", price=1000, owner_phone="+998901112233")
    )
    out = agency_service.list_objects(db, ag.id)
    assert out.total == 1
    # Владельцу платформы телефон собственника не показываем, остальное — да.
    assert out.items[0].owner_phone is None
    assert out.items[0].district == "Ч"
    assert out.items[0].added_via == "manual"
