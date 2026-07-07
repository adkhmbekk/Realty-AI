"""
Правка агентства (agency_service.update_settings: name → name+project_name,
owner_name → full_name владельца) и поиск по общей базе (mls_service.list_pool_for_member
с фильтрами rooms/price/type; контакты своих видны, чужих скрыты).
SQLite в памяти (фикстура db из conftest).
"""
from app.db.models.agency import Agency
from app.repositories import user_repo
from app.schemas.apartment import ApartmentCreate
from app.services import agency_service, apartment_service, mls_service


def _agency_with_owner(db, name, tg, owner_name="Старый Владелец"):
    ag = Agency(name=name, status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(ag)
    db.flush()
    ag.project_name = name
    owner = user_repo.create(
        db, telegram_id=tg, role="agency_admin", agency_id=ag.id,
        is_owner=True, full_name=owner_name,
    )
    db.commit()
    return ag, owner


def test_update_settings_name_and_owner(db):
    ag, owner = _agency_with_owner(db, "Старое имя", 201)
    agency_service.update_settings(
        db, ag.id, name="Новое агентство", owner_name="Иван Владелец",
        contact_phone="+998901112233",
    )
    db.refresh(ag)
    db.refresh(owner)
    # Название агентства = бренд: name и project_name синхронны.
    assert ag.name == "Новое агентство"
    assert ag.project_name == "Новое агентство"
    # Имя владельца обновилось.
    assert owner.full_name == "Иван Владелец"
    # Контактный телефон — как раньше.
    assert ag.contact_phone == "+998901112233"


def _mk(db, ag, owner, **extra):
    payload = ApartmentCreate(currency="USD", shared_mls=True, **extra)
    return apartment_service.create_apartment(db, ag.id, created_by=owner.id, payload=payload)


def test_mls_search_filters_and_contacts(db):
    a, ua = _agency_with_owner(db, "Alpha", 202)
    b, ub = _agency_with_owner(db, "Beta", 203)
    # Свой объект A: 2к / 50k / Квартира, с телефоном собственника.
    _mk(db, a, ua, type="Квартира", district="Чиланзар", rooms=2, price=50000, owner_phone="+998900000001")
    # Чужой B: 2к / 48k / Квартира.
    _mk(db, b, ub, type="Квартира", district="Юнусабад", rooms=2, price=48000, owner_phone="+998900000002")
    # Чужой B: 4к / 120k / Дом — под фильтр (1-2к, до 60k, Квартира) НЕ попадает.
    _mk(db, b, ub, type="Дом", district="Юнусабад", rooms=4, price=120000)

    out = mls_service.list_pool_for_member(
        db, a.id, rooms_min=1, rooms_max=2, price_max=60000, types=["Квартира"],
    )
    assert out.total == 2  # обе квартиры; дом отфильтрован
    by_agency = {it.agency_id: it for it in out.items}
    # Свой объект — телефон собственника виден.
    assert by_agency[a.id].apartment.owner_phone == "+998900000001"
    # Чужой объект — телефон скрыт.
    assert by_agency[b.id].apartment.owner_phone is None
