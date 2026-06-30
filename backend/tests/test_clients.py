"""
Тесты клиентской базы: создание клиента/заявки, авто-подбор по существующей
базе и по новым объектам (тик), видимость (агент видит своих, админ — всех),
дедуп совпадений и счётчик новых. На SQLite в памяти (фикстура db из conftest).
"""
import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.db.models.agency import Agency
from app.repositories import client_repo, user_repo
from app.schemas.apartment import ApartmentCreate
from app.schemas.client import ActivityCreate, ClientCreate, ClientUpdate, RequestCreate, RequestUpdate, TaskCreate
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


def test_delete_client_soft_archives(db):
    agency, admin, agent = _setup(db)
    _apt(db, agency.id, agent.id, type="Квартира", district="Юнусабад", rooms=5, price=100000, currency="USD")
    out, found = client_service.create_client(
        db, agency.id, agent, ClientCreate(name="Архивный", request=RequestCreate(districts=["Юнусабад"])),
    )
    assert found == 1
    req_id = client_service.get_client_detail(db, agency.id, agent, out.id).requests[0].id
    # «Удаление» = архивирование: клиент остаётся в БД, но пропадает из списка.
    client_service.delete_client(db, agency.id, agent, out.id)
    c = client_repo.get_client(db, agency.id, out.id)
    assert c is not None and c.status == "archived"
    assert all(x.id != out.id for x in client_service.list_clients(db, agency.id, agent))
    # История заявок сохранилась.
    assert client_repo.get_request(db, agency.id, req_id) is not None
    # Возврат из архива — статус active.
    client_service.update_client(db, agency.id, agent, out.id, ClientUpdate(status="active"))
    assert any(x.id == out.id for x in client_service.list_clients(db, agency.id, agent))


def test_owner_reassign_validated(db):
    agency, admin, agent = _setup(db)
    agency2 = Agency(name="B", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(agency2)
    db.flush()
    foreign = user_repo.create(db, telegram_id=77, role="agent", agency_id=agency2.id)
    db.commit()
    out, _ = client_service.create_client(db, agency.id, admin, ClientCreate(name="К"))
    # Несуществующий владелец — ошибка.
    with pytest.raises(AppError):
        client_service.update_client(db, agency.id, admin, out.id, ClientUpdate(owner_id=999999))
    # Сотрудник чужого агентства — ошибка.
    with pytest.raises(AppError):
        client_service.update_client(db, agency.id, admin, out.id, ClientUpdate(owner_id=foreign.id))
    # Свой активный агент — ок.
    res = client_service.update_client(db, agency.id, admin, out.id, ClientUpdate(owner_id=agent.id))
    assert res.created_by == agent.id


def test_invalid_statuses_rejected(db):
    agency, admin, agent = _setup(db)
    out, _ = client_service.create_client(
        db, agency.id, agent, ClientCreate(name="С", request=RequestCreate(districts=["Юнусабад"])),
    )
    req_id = client_service.get_client_detail(db, agency.id, agent, out.id).requests[0].id
    with pytest.raises(AppError):
        client_service.update_client(db, agency.id, agent, out.id, ClientUpdate(status="deleted"))
    with pytest.raises(AppError):
        client_service.update_request(db, agency.id, agent, req_id, RequestUpdate(status="done"))


def test_request_range_and_currency_validation(db):
    # min > max — отклоняется схемой (422).
    with pytest.raises(ValidationError):
        RequestCreate(rooms_min=5, rooms_max=2)
    with pytest.raises(ValidationError):
        RequestCreate(price_min=100000, price_max=50000)
    # Неизвестная валюта — отклоняется.
    with pytest.raises(ValidationError):
        RequestCreate(districts=["Юнусабад"], currency="RUB")


# ── Волна 2: приоритет и источник клиента ────────────────────────────
def test_client_priority_and_source(db):
    agency, admin, agent = _setup(db)
    out, _ = client_service.create_client(
        db, agency.id, agent, ClientCreate(name="Алия", priority="hot", source="Instagram"),
    )
    assert out.priority == "hot" and out.source == "Instagram"
    # Правка приоритета и источника.
    out2 = client_service.update_client(
        db, agency.id, agent, out.id, ClientUpdate(priority="cold", source="OLX"),
    )
    assert out2.priority == "cold" and out2.source == "OLX"
    # Очистка пустой строкой.
    out3 = client_service.update_client(db, agency.id, agent, out.id, ClientUpdate(priority=""))
    assert out3.priority is None
    out4 = client_service.update_client(db, agency.id, agent, out.id, ClientUpdate(source=""))
    assert out4.source is None


def test_client_invalid_priority_ignored(db):
    agency, admin, agent = _setup(db)
    out, _ = client_service.create_client(db, agency.id, agent, ClientCreate(name="Б", priority="warm"))
    out2 = client_service.update_client(db, agency.id, agent, out.id, ClientUpdate(priority="zzz"))
    assert out2.priority == "warm"  # некорректное значение игнорируется


# ── Волна 1: сквозной подбор по площади (квадратуре) + балл ───────────
def test_request_area_match_end_to_end(db):
    agency, admin, agent = _setup(db)
    _apt(db, agency.id, agent.id, type="Квартира", district="Юнусабад", rooms=3, area=90, price=70000, currency="USD")
    out, found = client_service.create_client(
        db, agency.id, agent,
        ClientCreate(name="Зара", request=RequestCreate(
            districts=["Юнусабад"], area_min=80, area_max=120, price_max=80000, currency="USD",
        )),
    )
    assert found == 1
    m = client_service.list_matches(db, agency.id, agent)[0]
    assert m.score == 100
    assert "area" in (m.match_good or [])


# ── Волна 3: лента действий по клиенту ───────────────────────────────
def test_client_activity_log(db):
    agency, admin, agent = _setup(db)
    out, _ = client_service.create_client(db, agency.id, agent, ClientCreate(name="Ник"))
    client_service.add_activity(db, agency.id, agent, out.id, ActivityCreate(kind="call", note="перезвонить завтра"))
    client_service.add_activity(db, agency.id, agent, out.id, ActivityCreate(kind="show"))
    acts = client_service.list_activities(db, agency.id, agent, out.id)
    assert len(acts) == 2
    assert acts[0].kind == "show"  # новые сверху
    assert acts[1].kind == "call" and acts[1].note == "перезвонить завтра"
    # Чужой агент не видит чужого клиента (и его историю).
    other = user_repo.create(db, telegram_id=3, role="agent", agency_id=agency.id)
    db.commit()
    with pytest.raises(AppError):
        client_service.list_activities(db, agency.id, other, out.id)


# ── Волна 4: задачи (ручные + авто «молчит N дней») ──────────────────
def test_client_tasks_and_autotask(db):
    from datetime import datetime, timedelta, timezone

    from app.db.models.client import Client as ClientModel

    agency, admin, agent = _setup(db)
    out, _ = client_service.create_client(
        db, agency.id, agent,
        ClientCreate(name="Лена", request=RequestCreate(districts=["Юнусабад"])),
    )
    # Ручная задача.
    t = client_service.add_task(db, agency.id, agent, out.id, TaskCreate(title="Позвонить"))
    assert t.status == "open" and t.kind == "manual"
    assert len(client_service.list_tasks_for_client(db, agency.id, agent, out.id)) == 1
    # Завершить → пропадает из «моих открытых».
    done = client_service.set_task_status(db, agency.id, agent, t.id, "done")
    assert done.status == "done"
    assert client_service.list_my_open_tasks(db, agency.id, agent) == []

    # Авто-задача: «состарим» клиента (нет действий 30 дней) → ставится «позвонить».
    cobj = db.get(ClientModel, out.id)
    cobj.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    db.commit()
    assert client_service.run_autotask_tick(db, idle_days=7) == 1
    autos = [x for x in client_service.list_tasks_for_client(db, agency.id, agent, out.id) if x.kind == "auto"]
    assert len(autos) == 1
    # Повторный тик не плодит дубль.
    assert client_service.run_autotask_tick(db, idle_days=7) == 0


# ── Волна 5: сделки и комиссия ───────────────────────────────────────
def test_client_deal_pipeline(db):
    from app.schemas.client import DealCreate, DealUpdate

    agency, admin, agent = _setup(db)
    apt = _apt(db, agency.id, agent.id, type="Квартира", district="Юнусабад", rooms=3, price=70000, currency="USD")
    out, _ = client_service.create_client(db, agency.id, agent, ClientCreate(name="Дима"))
    d = client_service.create_deal(
        db, agency.id, agent, out.id,
        DealCreate(apartment_id=apt.id, stage="interested", price=70000, currency="USD"),
    )
    assert d.stage == "interested" and d.apartment_id == apt.id
    assert d.agent_id == agent.id  # по умолчанию — владелец клиента
    # Этап → задаток (деньги), затем продано (закрытие фиксируется).
    d2 = client_service.update_deal(
        db, agency.id, agent, d.id, DealUpdate(stage="deposit", commission=2000, commission_currency="USD"),
    )
    assert d2.stage == "deposit" and d2.commission == 2000
    d3 = client_service.update_deal(db, agency.id, agent, d.id, DealUpdate(stage="sold"))
    assert d3.stage == "sold" and d3.closed_at is not None
    assert len(client_service.list_deals_for_client(db, agency.id, agent, out.id)) == 1
    assert len(client_service.list_my_deals(db, agency.id, agent)) == 1

    # Чужой объект (другого агентства) в сделку привязать нельзя.
    other = Agency(name="O2", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(other)
    db.flush()
    foreign = _apt(db, other.id, None, type="Квартира", price=1, currency="USD")
    with pytest.raises(AppError):
        client_service.create_deal(db, agency.id, agent, out.id, DealCreate(apartment_id=foreign.id))


# ── Волна 6: ИИ-подсказки по правилам ────────────────────────────────
def test_client_hints(db):
    from datetime import datetime, timedelta, timezone

    from app.db.models.client import Client as ClientModel

    agency, admin, agent = _setup(db)
    _apt(db, agency.id, agent.id, type="Квартира", district="Юнусабад", rooms=3, price=70000, currency="USD")
    out, _ = client_service.create_client(
        db, agency.id, agent,
        ClientCreate(name="Гена", request=RequestCreate(districts=["Юнусабад"], price_max=80000, currency="USD")),
    )
    kinds = {h.kind for h in client_service.client_hints(db, agency.id, agent, out.id)}
    assert "new_matches" in kinds  # есть новое совпадение

    # «Молчит»: состарим клиента (нет действий 20 дней).
    cobj = db.get(ClientModel, out.id)
    cobj.created_at = datetime.now(timezone.utc) - timedelta(days=20)
    db.commit()
    silent = [h for h in client_service.client_hints(db, agency.id, agent, out.id) if h.kind == "silent"]
    assert silent and silent[0].days >= 7

    # Клиент без активной заявки → подсказка no_request.
    out2, _ = client_service.create_client(db, agency.id, agent, ClientCreate(name="Без заявки"))
    assert any(h.kind == "no_request" for h in client_service.client_hints(db, agency.id, agent, out2.id))
