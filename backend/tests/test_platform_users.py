"""
Витрина «юзеры прошки» для владельца платформы (Фаза 5, 2026-07).

Проверяем: список юзеров исключает суперадминов; карточка юзера отдаёт ЕГО
объекты, но НЕ клиентскую базу (приватность арендаторов — решение владельца).
"""
import pytest

from app.core.errors import AppError
from app.db.models.agency import Agency
from app.db.models.apartment import Apartment
from app.repositories import agency_membership_repo, user_repo
from app.services import platform_service


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
