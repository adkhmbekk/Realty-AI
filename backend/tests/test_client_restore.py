"""Тесты «вернуть»: архивный клиент виден в архиве и восстанавливается;
отклонённое совпадение можно вернуть."""
from app.db.models.agency import Agency
from app.repositories import user_repo
from app.schemas.apartment import ApartmentCreate
from app.schemas.client import ClientCreate, ClientUpdate, RequestCreate
from app.services import apartment_service, client_service


def _setup(db):
    ag = Agency(name="R", status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(ag)
    db.flush()
    agent = user_repo.create(db, telegram_id=1, role="agent", agency_id=ag.id)
    db.commit()
    return ag, agent


def test_client_archive_list_and_restore(db):
    ag, agent = _setup(db)
    out, _ = client_service.create_client(db, ag.id, agent, ClientCreate(name="Архивный"))
    cid = out.id
    # Активный список — виден; архив — пуст.
    assert any(c.id == cid for c in client_service.list_clients(db, ag.id, agent))
    assert all(c.id != cid for c in client_service.list_clients(db, ag.id, agent, archived=True))
    # Архивируем (мягкое удаление).
    client_service.delete_client(db, ag.id, agent, cid)
    assert all(c.id != cid for c in client_service.list_clients(db, ag.id, agent))
    assert any(c.id == cid for c in client_service.list_clients(db, ag.id, agent, archived=True))
    # Возвращаем из архива (status -> active).
    client_service.update_client(db, ag.id, agent, cid, ClientUpdate(status="active"))
    assert any(c.id == cid for c in client_service.list_clients(db, ag.id, agent))
    assert all(c.id != cid for c in client_service.list_clients(db, ag.id, agent, archived=True))


def test_dismissed_match_restore(db):
    ag, agent = _setup(db)
    apartment_service.create_apartment(
        db, ag.id, created_by=agent.id,
        payload=ApartmentCreate(type="Квартира", district="Юнусабад", rooms=3, price=70000, currency="USD"),
    )
    out, found = client_service.create_client(
        db, ag.id, agent,
        ClientCreate(name="М", request=RequestCreate(districts=["Юнусабад"], price_max=80000, currency="USD")),
    )
    assert found == 1
    m = client_service.list_matches(db, ag.id, agent, statuses=["new"])[0]
    # Отклоняем — исчезает из активных, появляется в «отклонённых».
    client_service.set_match_status(db, ag.id, agent, m.id, "dismissed")
    assert client_service.list_matches(db, ag.id, agent, statuses=["new", "seen", "offered"]) == []
    assert len(client_service.list_matches(db, ag.id, agent, statuses=["dismissed"])) == 1
    # Возвращаем.
    client_service.set_match_status(db, ag.id, agent, m.id, "new")
    assert len(client_service.list_matches(db, ag.id, agent, statuses=["new"])) == 1
