"""
Тесты витрины общей базы (MLS) для владельца платформы (mls_service.list_pool):
видны объекты ВСЕХ агентств с shared_mls=True, контакты собственника скрыты,
не-shared и проданные не попадают, фильтр по агентству/типу сделки работает.
На SQLite в памяти (фикстура db из conftest).
"""
from app.db.models.agency import Agency
from app.repositories import user_repo
from app.schemas.apartment import ApartmentCreate
from app.services import apartment_service, mls_service


def _agency(db, name, tg):
    ag = Agency(name=name, status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(ag)
    db.flush()
    user = user_repo.create(db, telegram_id=tg, role="agent", agency_id=ag.id)
    db.commit()
    return ag, user


def test_mls_pool_lists_shared_across_agencies_with_blanked_contacts(db):
    a, ua = _agency(db, "Alpha", 1)
    b, ub = _agency(db, "Beta", 2)
    # A делится одним объектом (с контактами); B делится одним; у B есть НЕ-shared.
    apartment_service.create_apartment(
        db, a.id, created_by=ua.id,
        payload=ApartmentCreate(type="Квартира", district="Чиланзар", rooms=2, price=50000,
                                currency="USD", owner_phone="+998900000001",
                                address="ул. Тайная, 1", comment="внутр",
                                source_link="https://t.me/x/1", source="@x", shared_mls=True),
    )
    apartment_service.create_apartment(
        db, b.id, created_by=ub.id,
        payload=ApartmentCreate(type="Дом", district="Юнусабад", rooms=4, price=120000,
                                currency="USD", owner_phone="+998900000002",
                                address="ул. Скрытая, 2", shared_mls=True),
    )
    apartment_service.create_apartment(
        db, b.id, created_by=ub.id,
        payload=ApartmentCreate(type="Квартира", district="Юнусабад", rooms=1, price=30000,
                                currency="USD"),  # НЕ shared
    )

    out = mls_service.list_pool(db)
    assert out.total == 2
    assert len(out.items) == 2
    # Видно оба агентства-владельца.
    assert {it.agency_name for it in out.items} == {"Alpha", "Beta"}
    # Контакты/адрес/автор/внутренние поля скрыты у каждого; общее — остаётся.
    for it in out.items:
        ap = it.apartment
        assert ap.owner_phone is None
        assert ap.address is None
        assert ap.comment is None
        assert ap.source is None
        assert ap.source_link is None
        assert ap.created_by is None
        assert ap.created_by_name is None
        assert ap.district is not None
        assert ap.price is not None

    # Фильтр по агентству B → только объект B.
    only_b = mls_service.list_pool(db, agency_id=b.id)
    assert only_b.total == 1
    assert only_b.items[0].agency_name == "Beta"
    assert only_b.items[0].apartment.type == "Дом"

    # Фильтр по типу сделки: всё создано как продажа (sale) по умолчанию.
    assert mls_service.list_pool(db, deal_type="sale").total == 2
    assert mls_service.list_pool(db, deal_type="rent").total == 0


def test_mls_pool_excludes_sold(db):
    a, ua = _agency(db, "Gamma", 3)
    apartment_service.create_apartment(
        db, a.id, created_by=ua.id,
        payload=ApartmentCreate(type="Квартира", district="Сергели", rooms=2, price=40000,
                                currency="USD", shared_mls=True, status="sold"),
    )
    # По умолчанию витрина показывает активные → проданный не виден.
    assert mls_service.list_pool(db).total == 0
    assert mls_service.list_pool(db, status="active").total == 0


def test_mls_pool_scrubs_phone_from_free_text_fields(db):
    """Жёсткий ограничитель: телефон собственника не утекает через свободные
    поля (название/описание), даже если его вписали туда, а не в owner_phone."""
    a, ua = _agency(db, "Alpha", 11)
    apartment_service.create_apartment(
        db, a.id, created_by=ua.id,
        payload=ApartmentCreate(
            type="Квартира", district="Чиланзар", rooms=2, price=50000, currency="USD",
            name="Срочно, звоните 998901234567",
            description="Хороший ремонт, центр. Тел: +998 90 111 22 33",
            owner_phone="+998900000009",
            shared_mls=True,
        ),
    )
    ap = mls_service.list_pool(db).items[0].apartment

    def digits(s):
        return "".join(c for c in (s or "") if c.isdigit())

    # Ни один номер не просочился через свободные поля.
    assert "998901234567" not in digits(ap.name)
    assert "998901112233" not in digits(ap.description)
    # Осмысленный текст сохранён.
    assert ap.name and "Срочно" in ap.name
    assert ap.description and "ремонт" in ap.description
    # owner_phone по-прежнему полностью скрыт.
    assert ap.owner_phone is None
