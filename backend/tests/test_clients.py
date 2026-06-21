"""
Тесты клиентской базы: создание клиента/заявки, авто-подбор по существующей
базе и по новым объектам (тик), видимость (агент видит своих, админ — всех),
дедуп совпадений и счётчик новых. На SQLite в памяти (фикстура db из conftest).
"""
import pytest

from app.core.errors import AppError
from app.db.models.agency import Agency
from app.repositories import user_repo
from app.schemas.apartment import ApartmentCreate
from app.schemas.client import ClientCreate, RequestCreate
from app.services import apartment_service, client_service


def _setup(db):
    agency = Agency(name="A", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(agency)
    db.flush()
    admin = user_repo.create(db, telegram_id=1, role="agency_admin", agency_id=agency.id, is_owner=True)
    agent = user_repo.create(db, telegram_id=2, role="agent", agency_id=agency.id)
    db.commit()
    return agency, admin, agent


def _apt(db, aid, uid, **kw):
    return apartment_service.create_apartment(db, aid, created_by=uid, payload=ApartmentCreate(**kw))


def test_create_client_scans_existing_base(db):
    agency, admin, agent = _setup(db)
    _apt(db, agency.id, agent.id, type="Квартира", district="Юнусабад", rooms=5, price=100000, currency="USD")
    out, found = client_service.create_client(
        db, agency.id, agent,
        ClientCreate(
            name="Иван", phone="+998901112233",
            request=RequestCreate(
                types=["Квартира"], districts=["Юнусабад"],
                rooms_min=4, rooms_max=6, price_min=90000, price_max=120000, currency="USD",
            ),
        ),
    )
    assert found == 1
    assert out.new_match_count == 1
    matches = client_service.list_matches(db, agency.id, agent)
    assert len(matches) == 1
    assert matches[0].apartment.district == "Юнусабад"
    assert matches[0].client_name == "Иван"


def test_new_apartment_matches_via_tick(db):
    agency, admin, agent = _setup(db)
    out, found = client_service.create_client(
        db, agency.id, agent,
        ClientCreate(name="Пётр", request=RequestCreate(districts=["Чиланзар"], rooms_min=3)),
    )
    assert found == 0  # объектов ещё нет
    _apt(db, agency.id, agent.id, type="Квартира", district="Чиланзар", rooms=3, price=50000)
    created = client_service.run_matching_tick(db, lookback_minutes=100000)
    assert created == 1
    assert client_service.new_match_count(db, agency.id, agent) == 1
    # повторный тик не плодит дубли
    assert client_service.run_matching_tick(db, lookback_minutes=100000) == 0


def test_currency_and_room_bounds(db):
    agency, admin, agent = _setup(db)
    _apt(db, agency.id, agent.id, type="Квартира", district="Мирабад", rooms=2, price=80000, currency="USD")
    # Заявка в UZS — не должна совпасть (валюта другая).
    out, found = client_service.create_client(
        db, agency.id, agent,
        ClientCreate(name="A", request=RequestCreate(districts=["Мирабад"], price_min=70000, price_max=90000, currency="UZS")),
    )
    assert found == 0
    # Заявка с комнатами 3+ — не совпадёт (в объекте 2).
    out2, found2 = client_service.create_client(
        db, agency.id, agent,
        ClientCreate(name="B", request=RequestCreate(districts=["Мирабад"], rooms_min=3)),
    )
    assert found2 == 0
    # Заявка USD с подходящим диапазоном — совпадёт.
    out3, found3 = client_service.create_client(
        db, agency.id, agent,
        ClientCreate(name="C", request=RequestCreate(districts=["Мирабад"], rooms_min=2, rooms_max=2, currency="USD", price_min=70000, price_max=90000)),
    )
    assert found3 == 1


def test_visibility_agent_vs_admin(db):
    agency, admin, agent = _setup(db)
    client_service.create_client(db, agency.id, agent, ClientCreate(name="Свой"))
    client_service.create_client(db, agency.id, admin, ClientCreate(name="Админский"))
    agent_list = client_service.list_clients(db, agency.id, agent)
    admin_list = client_service.list_clients(db, agency.id, admin)
    assert len(agent_list) == 1 and agent_list[0].name == "Свой"
    assert len(admin_list) == 2
    # Агент не может открыть чужого клиента (как будто его нет).
    others = [c for c in admin_list if c.name == "Админский"][0]
    with pytest.raises(AppError):
        client_service.get_client_detail(db, agency.id, agent, others.id)


def test_empty_request_rejected(db):
    agency, admin, agent = _setup(db)
    out, _ = client_service.create_client(db, agency.id, agent, ClientCreate(name="X"))
    with pytest.raises(AppError):
        client_service.add_request(db, agency.id, agent, out.id, RequestCreate(note="просто текст"))


def test_dedup_and_mark_seen(db):
    agency, admin, agent = _setup(db)
    _apt(db, agency.id, agent.id, type="Квартира", district="Юнусабад", rooms=5, price=100000, currency="USD")
    out, found = client_service.create_client(
        db, agency.id, agent, ClientCreate(name="И", request=RequestCreate(districts=["Юнусабад"])),
    )
    assert found == 1
    detail = client_service.get_client_detail(db, agency.id, agent, out.id)
    req_id = detail.requests[0].id
    # Повторный подбор по той же базе — без новых.
    assert client_service.rescan_request(db, agency.id, agent, req_id) == 0
    assert client_service.new_match_count(db, agency.id, agent) == 1
    client_service.mark_all_seen(db, agency.id, agent)
    assert client_service.new_match_count(db, agency.id, agent) == 0


def test_isolation_between_agencies(db):
    a1, admin1, agent1 = _setup(db)
    agency2 = Agency(name="B", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(agency2)
    db.flush()
    agent2 = user_repo.create(db, telegram_id=99, role="agent", agency_id=agency2.id)
    db.commit()
    # Объект в агентстве 2.
    _apt(db, agency2.id, agent2.id, type="Квартира", district="Юнусабад", rooms=5, price=100000, currency="USD")
    # Заявка клиента в агентстве 1 НЕ должна цеплять чужой объект.
    out, found = client_service.create_client(
        db, a1.id, agent1, ClientCreate(name="И", request=RequestCreate(districts=["Юнусабад"])),
    )
    assert found == 0
    assert client_service.run_matching_tick(db, lookback_minutes=100000) == 0
