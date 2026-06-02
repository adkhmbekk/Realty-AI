"""
Тесты поиска: фильтр по валюте (цена сравнивается в рамках одной валюты) и
поиск по номеру собственника. На SQLite в памяти (фикстура db из conftest).
"""
from app.db.models.agency import Agency
from app.repositories import apartment_repo, user_repo
from app.schemas.apartment import ApartmentCreate
from app.services import apartment_service


def _setup(db):
    agency = Agency(name="A", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(agency)
    db.flush()
    admin = user_repo.create(db, telegram_id=1, role="agency_admin", agency_id=agency.id, is_owner=True)
    db.commit()
    return agency.id, admin.id


def test_owner_phone_search(db):
    aid, uid = _setup(db)
    apartment_service.create_apartment(
        db, aid, created_by=uid,
        payload=ApartmentCreate(name="С телефоном", owner_phone="+998901112233"),
    )
    apartment_service.create_apartment(
        db, aid, created_by=uid, payload=ApartmentCreate(name="Без телефона"),
    )

    items, total = apartment_repo.search(db, aid, status=None, q="1112233")
    assert total == 1 and items[0].owner_phone == "+998901112233"
    # Несуществующий номер ничего не находит.
    _, none = apartment_repo.search(db, aid, status=None, q="0000000")
    assert none == 0


def test_currency_filter(db):
    aid, uid = _setup(db)
    apartment_service.create_apartment(
        db, aid, created_by=uid, payload=ApartmentCreate(price=50000, currency="USD"),
    )
    apartment_service.create_apartment(
        db, aid, created_by=uid, payload=ApartmentCreate(price=50000, currency="UZS"),
    )

    usd, usd_total = apartment_repo.search(db, aid, status=None, currency="USD")
    assert usd_total == 1 and usd[0].currency == "USD"

    # Без фильтра валюты видны оба (цена 50000 в обеих валютах).
    _, both = apartment_repo.search(db, aid, status=None)
    assert both == 2

    # Фильтр цены в рамках валюты: 50000 USD попадает в диапазон, UZS отсечён валютой.
    _, in_range = apartment_repo.search(
        db, aid, status=None, currency="USD", price_min=40000, price_max=60000
    )
    assert in_range == 1


def test_archived_status_rejected(db):
    """После удаления архива создать объект со статусом 'archived' нельзя."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ApartmentCreate(status="archived")
