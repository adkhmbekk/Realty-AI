"""
Тесты новых функций: архив (мягкое удаление/восстановление/удаление-навсегда),
@username владельца в карточке для шаринга, свод платежей по агентствам.
SQLite в памяти (фикстура db из conftest).
"""
from decimal import Decimal

from app.db.models.agency import Agency
from app.repositories import apartment_repo, payment_repo, user_repo
from app.schemas.apartment import ApartmentCreate
from app.services import agency_service, apartment_service


def _setup(db, *, username=None):
    agency = Agency(name="A", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(agency)
    db.flush()
    owner = user_repo.create(
        db, telegram_id=1, role="agency_admin", agency_id=agency.id, is_owner=True, username=username
    )
    db.commit()
    return agency.id, owner.id


def test_archive_hides_from_base_and_search(db):
    aid, uid = _setup(db)
    a1 = apartment_service.create_apartment(db, aid, created_by=uid, payload=ApartmentCreate(name="Раз"))
    apartment_service.create_apartment(db, aid, created_by=uid, payload=ApartmentCreate(name="Два"))

    # Изначально оба в базе, архив пуст.
    _, total = apartment_repo.search(db, aid, status=None)
    assert total == 2
    _, arch_total = apartment_repo.list_archived(db, aid)
    assert arch_total == 0

    # Удаляем один → он исчезает из базы/поиска и попадает в архив.
    apartment_service.delete_apartment(db, aid, a1.id)
    _, total = apartment_repo.search(db, aid, status=None)
    assert total == 1
    items, arch_total = apartment_repo.list_archived(db, aid)
    assert arch_total == 1 and items[0].id == a1.id


def test_restore_and_purge(db):
    aid, uid = _setup(db)
    a1 = apartment_service.create_apartment(db, aid, created_by=uid, payload=ApartmentCreate(name="Объект"))

    apartment_service.delete_apartment(db, aid, a1.id)
    # Восстановление возвращает объект в базу.
    apartment_service.restore_apartment(db, aid, a1.id)
    _, total = apartment_repo.search(db, aid, status=None)
    assert total == 1
    _, arch_total = apartment_repo.list_archived(db, aid)
    assert arch_total == 0

    # Удаление навсегда убирает объект из базы и из архива.
    apartment_service.delete_apartment(db, aid, a1.id)
    apartment_service.purge_apartment(db, aid, a1.id)
    _, arch_total = apartment_repo.list_archived(db, aid)
    assert arch_total == 0
    _, total = apartment_repo.search(db, aid, status=None)
    assert total == 0


def test_share_card_includes_owner_username(db):
    aid, uid = _setup(db, username="boss")
    # Контактный телефон агентства.
    agency = agency_repo_get(db, aid)
    agency.contact_phone = "+998900000000"
    db.commit()
    a1 = apartment_service.create_apartment(db, aid, created_by=uid, payload=ApartmentCreate(name="Объект"))
    card = apartment_service.build_share_card(db, aid, a1.id)
    assert card["contact_username"] == "@boss"
    assert "@boss" in card["share_text"]


def test_share_card_no_username_when_absent(db):
    aid, uid = _setup(db, username=None)
    a1 = apartment_service.create_apartment(db, aid, created_by=uid, payload=ApartmentCreate(name="Объект"))
    card = apartment_service.build_share_card(db, aid, a1.id)
    assert card["contact_username"] is None


def test_payments_summary(db):
    aid, _ = _setup(db)
    payment_repo.add(db, agency_id=aid, action="extend", days=30, amount=Decimal("100"), currency="USD")
    payment_repo.add(db, agency_id=aid, action="extend", days=30, amount=Decimal("50"), currency="USD")
    payment_repo.add(db, agency_id=aid, action="extend", days=30, amount=Decimal("200000"), currency="UZS")
    db.commit()

    s = agency_service.payments_summary(db)
    by_cur = {row["currency"]: row for row in s["all_time"]}
    assert by_cur["USD"]["amount"] == 150.0 and by_cur["USD"]["count"] == 2
    assert by_cur["UZS"]["amount"] == 200000.0 and by_cur["UZS"]["count"] == 1
    assert s["total_records"] == 3


def agency_repo_get(db, aid):
    from app.repositories import agency_repo

    return agency_repo.get_by_id(db, aid)
