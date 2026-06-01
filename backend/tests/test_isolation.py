"""
Тесты ИЗОЛЯЦИИ АГЕНТСТВ: одно агентство никогда не должно видеть данные другого.

Это ключевая гарантия мультиарендности (multi-tenant): все запросы к данным
обязаны фильтроваться по agency_id. Здесь мы заводим два агентства (A и B) с
их пользователями, объектами, справочниками и приглашениями и проверяем, что
выборки одного агентства не возвращают чужие записи.

Используется временная база SQLite в памяти — тесты не требуют PostgreSQL и
проходят в CI. Изоляция обеспечивается логикой репозиториев (WHERE agency_id=…),
которая одинакова для SQLite и PostgreSQL.
"""
import os

os.environ.setdefault("PHOTOS_DIR", "/tmp/realty_test_photos")

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.errors import AppError  # noqa: E402
from app.db import models  # noqa: F401, E402  — регистрирует все модели
from app.db.base import Base  # noqa: E402
from app.db.models.agency import Agency  # noqa: E402
from app.repositories import (  # noqa: E402
    apartment_repo,
    dictionary_repo,
    invite_repo,
    user_repo,
)
from app.schemas.apartment import ApartmentCreate  # noqa: E402
from app.services import apartment_service  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402


# В SQLite автоинкремент работает только у INTEGER PRIMARY KEY, а наши ключи —
# BigInteger. Это правило (ТОЛЬКО для диалекта sqlite, т.е. только в тестах)
# заставляет BigInteger компилироваться как INTEGER. На PostgreSQL не влияет.
@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(type_, compiler, **kw):  # noqa: ANN001
    return "INTEGER"


@pytest.fixture()
def db():
    """Чистая БД SQLite в памяти на каждый тест (общая на все соединения)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_agency(db, name: str) -> int:
    agency = Agency(name=name, status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(agency)
    db.flush()
    return agency.id


@pytest.fixture()
def two_agencies(db):
    """Два агентства A и B, у каждого — админ, объект, район, приглашение."""
    a = _make_agency(db, "Агентство A")
    b = _make_agency(db, "Агентство B")

    admin_a = user_repo.create(db, telegram_id=1001, role="agency_admin", agency_id=a, is_owner=True)
    admin_b = user_repo.create(db, telegram_id=2001, role="agency_admin", agency_id=b, is_owner=True)

    apt_a = apartment_service.create_apartment(
        db, a, created_by=admin_a.id,
        payload=ApartmentCreate(district="Чиланзар", type="Квартира", rooms=2, price=50000),
    )
    apt_b = apartment_service.create_apartment(
        db, b, created_by=admin_b.id,
        payload=ApartmentCreate(district="Юнусабад", type="Дом", rooms=4, price=90000),
    )

    dict_a = dictionary_repo.create(db, a, category="district", value="Чиланзар")
    dict_b = dictionary_repo.create(db, b, category="district", value="Юнусабад")

    inv_a = invite_repo.create(
        db, agency_id=a, code="CODE_A", role="agent", created_by=admin_a.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    inv_b = invite_repo.create(
        db, agency_id=b, code="CODE_B", role="agent", created_by=admin_b.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.commit()
    return {
        "a": a, "b": b,
        "admin_a": admin_a, "admin_b": admin_b,
        "apt_a": apt_a, "apt_b": apt_b,
        "dict_a": dict_a, "dict_b": dict_b,
        "inv_a": inv_a, "inv_b": inv_b,
    }


# ─── Объекты ─────────────────────────────────────────────────────────────
def test_apartment_search_isolated(db, two_agencies):
    a, b = two_agencies["a"], two_agencies["b"]
    items_a, total_a = apartment_repo.search(db, a, status=None)
    items_b, total_b = apartment_repo.search(db, b, status=None)
    assert total_a == 1 and total_b == 1
    assert {x.agency_id for x in items_a} == {a}
    assert {x.agency_id for x in items_b} == {b}
    # display_id одного агентства не пересекается в выборке другого.
    assert two_agencies["apt_b"].id not in {x.id for x in items_a}


def test_apartment_get_by_id_cross_agency_is_none(db, two_agencies):
    a = two_agencies["a"]
    foreign_id = two_agencies["apt_b"].id
    assert apartment_repo.get_by_id(db, a, foreign_id) is None
    # А свой объект — доступен.
    assert apartment_repo.get_by_id(db, a, two_agencies["apt_a"].id) is not None


def test_apartment_service_get_cross_agency_raises(db, two_agencies):
    a = two_agencies["a"]
    with pytest.raises(AppError) as ei:
        apartment_service.get_apartment(db, a, two_agencies["apt_b"].id)
    assert ei.value.status_code == 404


def test_apartment_filter_does_not_leak(db, two_agencies):
    # Фильтр по чужому району не возвращает чужие объекты.
    a = two_agencies["a"]
    items, total = apartment_repo.search(db, a, status=None, districts=["Юнусабад"])
    assert total == 0 and items == []


def test_status_change_isolated(db, two_agencies):
    # Нельзя сменить статус чужого объекта (объект «не найден» для другого агентства).
    a = two_agencies["a"]
    with pytest.raises(AppError) as ei:
        apartment_service.set_status(db, a, two_agencies["apt_b"].id, "sold")
    assert ei.value.status_code == 404


# ─── Справочники ─────────────────────────────────────────────────────────
def test_dictionary_isolated(db, two_agencies):
    a = two_agencies["a"]
    all_a = dictionary_repo.get_all(db, a)
    assert {d.agency_id for d in all_a} == {a}
    # Чужой элемент справочника по id недоступен.
    assert dictionary_repo.get_by_id(db, a, two_agencies["dict_b"].id) is None
    # get_one не находит чужое значение даже при совпадении категории.
    assert dictionary_repo.get_one(db, a, "district", "Юнусабад") is None


# ─── Команда (пользователи) ──────────────────────────────────────────────
def test_member_isolated(db, two_agencies):
    a = two_agencies["a"]
    # Чужой сотрудник по id недоступен в своём агентстве.
    assert user_repo.get_member(db, a, two_agencies["admin_b"].id) is None
    assert user_repo.get_member(db, a, two_agencies["admin_a"].id) is not None
    members_a = user_repo.get_by_agency(db, a)
    assert {u.agency_id for u in members_a} == {a}


# ─── Приглашения ─────────────────────────────────────────────────────────
def test_invite_isolated(db, two_agencies):
    a = two_agencies["a"]
    assert invite_repo.get_by_id(db, a, two_agencies["inv_b"].id) is None
    assert invite_repo.get_by_id(db, a, two_agencies["inv_a"].id) is not None
    all_a = invite_repo.get_all(db, a)
    assert {i.agency_id for i in all_a} == {a}


# ─── Ключевая логика ─────────────────────────────────────────────────────
def test_display_id_is_per_agency_sequential(db, two_agencies):
    """Номера объектов идут по порядку и НЕЗАВИСИМО в каждом агентстве."""
    a, b = two_agencies["a"], two_agencies["b"]
    # У обоих уже есть по одному объекту "0001".
    assert two_agencies["apt_a"].display_id == "0001"
    assert two_agencies["apt_b"].display_id == "0001"
    # Следующий объект в A — "0002", в B по-прежнему свой счётчик.
    apt_a2 = apartment_service.create_apartment(
        db, a, created_by=two_agencies["admin_a"].id, payload=ApartmentCreate(type="Квартира")
    )
    apt_b2 = apartment_service.create_apartment(
        db, b, created_by=two_agencies["admin_b"].id, payload=ApartmentCreate(type="Дом")
    )
    assert apt_a2.display_id == "0002"
    assert apt_b2.display_id == "0002"


def test_status_lifecycle_sets_archived_at(db, two_agencies):
    """Перевод в 'sold'/'archived' проставляет дату снятия, возврат — очищает."""
    a = two_agencies["a"]
    apt_id = two_agencies["apt_a"].id
    sold = apartment_service.set_status(db, a, apt_id, "sold", actor_id=two_agencies["admin_a"].id)
    assert sold.status == "sold" and sold.archived_at is not None
    back = apartment_service.set_status(db, a, apt_id, "active", actor_id=two_agencies["admin_a"].id)
    assert back.status == "active" and back.archived_at is None
