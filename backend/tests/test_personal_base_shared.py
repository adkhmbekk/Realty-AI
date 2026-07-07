"""
Личная база («Моя база») НЕ показывает объекты, которыми агент поделился в общей
базе (shared_mls=True): ни в списке (apartment_service.search_apartments), ни в
счётчиках (get_stats). Снятие «поделиться» возвращает объект в личную базу. Архив
остаётся полным (удалённый расшаренный объект восстановим). Общая база (MLS) при
этом по-прежнему показывает объект владельцу с контактом собственника.
На SQLite в памяти (фикстура db из conftest).
"""
from app.db.models.agency import Agency
from app.repositories import user_repo
from app.schemas.apartment import ApartmentCreate, ApartmentUpdate
from app.services import apartment_service, mls_service


def _agency(db, name, tg):
    ag = Agency(name=name, status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(ag)
    db.flush()
    user = user_repo.create(db, telegram_id=tg, role="agent", agency_id=ag.id)
    db.commit()
    return ag, user


def _mk(db, ag, user, *, shared, **extra):
    payload = ApartmentCreate(
        type="Квартира", district="Чиланзар", rooms=2, price=50000,
        currency="USD", shared_mls=shared, **extra,
    )
    return apartment_service.create_apartment(db, ag.id, created_by=user.id, payload=payload)


def test_personal_base_hides_shared_objects(db):
    ag, user = _agency(db, "Alpha", 101)
    _mk(db, ag, user, shared=False, name="личный")
    _mk(db, ag, user, shared=True, name="в общей базе", owner_phone="+998900000001")

    # В списке личной базы — только нерасшаренный объект.
    items, total = apartment_service.search_apartments(db, ag.id)
    assert total == 1
    assert [a.name for a in items] == ["личный"]

    # Счётчики карточки «Моя база» — тоже без расшаренного.
    stats = apartment_service.get_stats(db, ag.id)
    assert stats["active"] == 1
    assert stats["total"] == 1


def test_unshare_returns_object_to_personal_base(db):
    ag, user = _agency(db, "Beta", 102)
    apt = _mk(db, ag, user, shared=True, name="объект", owner_phone="+998900000002")

    # Пока расшарен — в личной базе его нет.
    _, total = apartment_service.search_apartments(db, ag.id)
    assert total == 0

    # Снимаем «поделиться» → объект вернулся в личную базу.
    apartment_service.update_apartment(db, ag.id, apt.id, ApartmentUpdate(shared_mls=False))
    items, total = apartment_service.search_apartments(db, ag.id)
    assert total == 1
    assert items[0].id == apt.id
    assert apartment_service.get_stats(db, ag.id)["total"] == 1


def test_shared_object_still_visible_to_owner_in_mls(db):
    ag, user = _agency(db, "Gamma", 103)
    _mk(db, ag, user, shared=True, name="в пуле", owner_phone="+998900000003")

    # Владелец видит свой объект в общей базе С контактом собственника (регрессия).
    out = mls_service.list_pool_for_member(db, ag.id)
    assert out.total == 1
    assert out.items[0].apartment.owner_phone == "+998900000003"


def test_archive_still_shows_shared_objects(db):
    """Архив («корзина») полный: удалённый расшаренный объект остаётся восстановимым."""
    ag, user = _agency(db, "Delta", 104)
    apt = _mk(db, ag, user, shared=True, name="удаляемый")
    apartment_service.delete_apartment(db, ag.id, apt.id)  # мягкое удаление в архив

    items, total = apartment_service.search_apartments(
        db, ag.id, status_filter=None, archived=True
    )
    assert total == 1
    assert items[0].id == apt.id
