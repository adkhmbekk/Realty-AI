"""
Витрина «юзеры прошки» для владельца платформы (Фаза 5, 2026-07).

Главный экран суперадмина в юзер-центричной модели — список юзеров (а не
агентств). Тап по юзеру → его агентства/роли и ЕГО объекты.

Приватность (решение владельца): отдаём только ОБЪЕКТЫ (листинги). Клиентскую
базу (CRM) НЕ отдаём — она приватна внутри агентства. Инвариант: этот модуль
НИКОГДА не обращается к клиентам/заявкам/сделкам.
"""
from typing import Optional

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.repositories import agency_membership_repo, apartment_repo, user_repo


def _user_summary(u) -> dict:
    return {
        "id": u.id,
        "telegram_id": u.telegram_id,
        "username": u.username,
        "full_name": u.full_name,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "phone": u.phone,
        "is_active": u.is_active,
        "last_seen_at": u.last_seen_at,
        "created_at": u.created_at,
        "agencies_count": 0,
    }


def list_platform_users(
    db: Session, *, q: Optional[str] = None, limit: int = 50, offset: int = 0
) -> dict:
    users, total = user_repo.list_all(db, q=q, limit=limit, offset=offset)
    counts = agency_membership_repo.counts_for_users(db, [u.id for u in users])
    items = []
    for u in users:
        d = _user_summary(u)
        d["agencies_count"] = counts.get(u.id, 0)
        items.append(d)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_platform_user(db: Session, user_id: int) -> dict:
    u = user_repo.get_by_id(db, user_id)
    # Суперадминов в этой витрине не показываем (это «юзеры прошки»).
    if u is None or u.role == "superadmin":
        raise AppError("user_not_found_or_inactive", status.HTTP_404_NOT_FOUND)

    memberships = agency_membership_repo.list_for_user(db, u.id)
    agencies = [
        {
            "agency_id": a.id,
            "agency_name": a.name,
            "role": m.role,
            "is_owner": m.is_owner,
        }
        for m, a in memberships
    ]
    # ТОЛЬКО объекты. Клиентов/заявки/сделки НЕ трогаем (приватность арендаторов).
    objects, objects_total = apartment_repo.list_by_creator(db, u.id, limit=100)

    summary = _user_summary(u)
    summary["agencies_count"] = len(memberships)
    return {
        "user": summary,
        "agencies": agencies,
        "objects": objects,
        "objects_total": objects_total,
    }
