"""
Витрина «юзеры прошки» для владельца платформы (Фаза 5, 2026-07).

Проверяем: список юзеров исключает суперадминов; карточка юзера отдаёт ЕГО
объекты, но НЕ клиентскую базу (приватность арендаторов — решение владельца).
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.errors import AppError
from app.db.models.agency import Agency
from app.db.models.apartment import Apartment
from app.repositories import agency_membership_repo, user_repo
from app.services import platform_service


def _ago(**kw):
    return datetime.now(timezone.utc) - timedelta(**kw)


def _agency(db, name="Клиент"):
    a = Agency(
        name=name, status="active", timezone="Asia/Tashkent", default_currency="USD"
    )
    db.add(a)
    db.commit()
    return a


def test_list_platform_users_excludes_superadmin(db):
    su = user_repo.create(db, telegram_id=100, role="superadmin")
    a = _agency(db)
    u = user_repo.create(db, telegram_id=101, role="agent", agency_id=a.id, full_name="Азиз")
    db.commit()

    r = platform_service.list_platform_users(db)
    ids = [i["id"] for i in r["items"]]
    assert u.id in ids
    assert su.id not in ids


def test_user_detail_exposes_objects_not_clients(db):
    a = _agency(db)
    u = user_repo.create(db, telegram_id=102, role="agent", agency_id=a.id)
    agency_membership_repo.create(db, user_id=u.id, agency_id=a.id, role="agent")
    apt = Apartment(agency_id=a.id, display_id="1", created_by=u.id)
    db.add(apt)
    db.commit()

    d = platform_service.get_platform_user(db, u.id)
    # Приватность: клиентская база НЕ отдаётся.
    assert "clients" not in d
    # Объекты юзера видны.
    assert d["objects_total"] == 1
    assert d["objects"][0].created_by == u.id
    # Агентства и счётчик.
    assert d["agencies"][0]["agency_id"] == a.id
    assert d["user"]["agencies_count"] == 1


def test_user_detail_404_for_superadmin_or_missing(db):
    su = user_repo.create(db, telegram_id=103, role="superadmin")
    db.commit()
    with pytest.raises(AppError) as exc:
        platform_service.get_platform_user(db, su.id)
    assert exc.value.status_code == 404
    with pytest.raises(AppError):
        platform_service.get_platform_user(db, 999999)


# ── Присутствие «в сети» (online / recent / offline) ──────────────────────────
def test_presence_online_recent_offline(db):
    a = _agency(db)
    on = user_repo.create(db, telegram_id=201, role="agent", agency_id=a.id, full_name="Онлайн")
    rec = user_repo.create(db, telegram_id=202, role="agent", agency_id=a.id, full_name="Рек")
    off = user_repo.create(db, telegram_id=203, role="agent", agency_id=a.id, full_name="Офлайн")
    on.last_seen_at = _ago(seconds=30)      # ≤3 мин → online
    rec.last_seen_at = _ago(seconds=210)    # 3–4 мин → recent
    off.last_seen_at = _ago(hours=1)        # давно → offline
    db.commit()

    by_id = {i["id"]: i["presence"] for i in platform_service.list_platform_users(db)["items"]}
    assert by_id[on.id] == "online"
    assert by_id[rec.id] == "recent"
    assert by_id[off.id] == "offline"


# ── Вовлечённость (тиры) + фолбэк last_login_at ───────────────────────────────
def test_engagement_tiers_and_login_fallback(db):
    a = _agency(db)
    act = user_repo.create(db, telegram_id=211, role="agent", agency_id=a.id, full_name="Активный")
    qui = user_repo.create(db, telegram_id=212, role="agent", agency_id=a.id, full_name="Притих")
    asl = user_repo.create(db, telegram_id=213, role="agent", agency_id=a.id, full_name="Спит")
    old = user_repo.create(db, telegram_id=214, role="agent", agency_id=a.id, full_name="Давно")
    nev = user_repo.create(db, telegram_id=215, role="agent", agency_id=a.id, full_name="Никогда")
    fbk = user_repo.create(db, telegram_id=216, role="agent", agency_id=a.id, full_name="Фолбэк")
    act.last_seen_at = _ago(days=1)     # ≤3 дн → active
    qui.last_seen_at = _ago(days=5)     # 3–10 → quiet
    asl.last_seen_at = _ago(days=20)    # 10–30 → asleep
    old.last_seen_at = _ago(days=40)    # >30 → never
    # nev — без last_seen/last_login → never
    fbk.last_login_at = _ago(days=1)    # last_seen нет, но заходил → active
    db.commit()

    items = platform_service.list_platform_users(db)
    by_id = {i["id"]: i["engagement"] for i in items["items"]}
    assert by_id[act.id] == "active"
    assert by_id[qui.id] == "quiet"
    assert by_id[asl.id] == "asleep"
    assert by_id[old.id] == "never"
    assert by_id[nev.id] == "never"
    assert by_id[fbk.id] == "active"
    # Агрегатная сводка по ВСЕМ активным юзерам.
    assert items["stats"] == {"active": 2, "quiet": 1, "asleep": 1, "never": 2}


def test_stats_count_all_users_not_page(db):
    a = _agency(db)
    for tg in (221, 222, 223):
        u = user_repo.create(db, telegram_id=tg, role="agent", agency_id=a.id)
        u.last_seen_at = _ago(days=1)
    db.commit()

    r = platform_service.list_platform_users(db, limit=1)
    assert len(r["items"]) == 1          # страница ограничена
    assert r["stats"]["active"] == 3     # но сводка — по всем


def test_engagement_filter_server_side(db):
    a = _agency(db)
    act = user_repo.create(db, telegram_id=231, role="agent", agency_id=a.id)
    asl = user_repo.create(db, telegram_id=232, role="agent", agency_id=a.id)
    act.last_seen_at = _ago(days=1)
    asl.last_seen_at = _ago(days=20)
    db.commit()

    r = platform_service.list_platform_users(db, engagement="asleep")
    ids = [i["id"] for i in r["items"]]
    assert ids == [asl.id]
    # Сводка НЕ зависит от фильтра — считает по всем.
    assert r["stats"] == {"active": 1, "quiet": 0, "asleep": 1, "never": 0}


def test_archived_tab_has_no_stats(db):
    a = _agency(db)
    u = user_repo.create(db, telegram_id=241, role="agent", agency_id=a.id)
    u.last_seen_at = _ago(days=1)
    db.commit()
    platform_service.archive_user(db, u.id)

    r = platform_service.list_platform_users(db, archived=True)
    assert r["stats"] is None
    assert [i["id"] for i in r["items"]] == [u.id]
