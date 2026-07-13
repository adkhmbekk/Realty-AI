"""
Витрина «юзеры прошки» для владельца платформы (Фаза 5, 2026-07).

Главный экран суперадмина в юзер-центричной модели — список юзеров (а не
агентств). Тап по юзеру → его агентства/роли и ЕГО объекты.

Приватность (решение владельца): отдаём только ОБЪЕКТЫ (листинги). Клиентскую
базу (CRM) НЕ отдаём — она приватна внутри агентства. Инвариант: этот модуль
НИКОГДА не обращается к клиентам/заявкам/сделкам.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.repositories import agency_membership_repo, apartment_repo, user_repo
from app.services import user_presence


def _user_summary(u, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
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
        "last_active_at": user_presence.latest(u.last_seen_at, u.last_login_at),
        "created_at": u.created_at,
        "archived_at": u.archived_at,
        "agencies_count": 0,
        "presence": user_presence.presence(u.last_seen_at, now),
        "engagement": user_presence.engagement(u.last_seen_at, u.last_login_at, now),
    }


def _engagement_stats(db: Session, now: datetime) -> dict:
    """Сводка по тирам вовлечённости по ВСЕМ активным юзерам (не по странице)."""
    stats = {tier: 0 for tier in user_presence.ENGAGEMENT_TIERS}
    for last_seen_at, last_login_at in user_repo.presence_signals_active(db):
        stats[user_presence.engagement(last_seen_at, last_login_at, now)] += 1
    return stats


def list_platform_users(
    db: Session, *, q: Optional[str] = None, archived: bool = False,
    engagement: Optional[str] = None, limit: int = 50, offset: int = 0,
) -> dict:
    now = datetime.now(timezone.utc)
    # Серверный фильтр по тиру (консистентен с пагинацией и агрегатом). В архиве
    # тир нерелевантен — фильтр игнорируем.
    extra = None
    if engagement and not archived:
        cond = user_presence.engagement_condition(engagement, now)
        if cond is not None:
            extra = [cond]
    users, total = user_repo.list_all(
        db, q=q, archived=archived, extra=extra, limit=limit, offset=offset
    )
    counts = agency_membership_repo.counts_for_users(db, [u.id for u in users])
    items = []
    for u in users:
        d = _user_summary(u, now)
        d["agencies_count"] = counts.get(u.id, 0)
        items.append(d)
    # Плашка-сводка — только для активной вкладки (в архиве присутствие/тир не нужны).
    stats = None if archived else _engagement_stats(db, now)
    return {
        "items": items, "total": total, "limit": limit, "offset": offset,
        "stats": stats,
    }


def get_platform_user(db: Session, user_id: int) -> dict:
    u = user_repo.get_by_id(db, user_id)
    # Суперадминов в этой витрине не показываем (это «юзеры прошки»). Архивных —
    # показываем (карточка в архиве), поэтому include_archived=True для их агентств.
    if u is None or u.role == "superadmin":
        raise AppError("user_not_found_or_inactive", status.HTTP_404_NOT_FOUND)

    memberships = agency_membership_repo.list_for_user(db, u.id, include_archived=True)
    agencies = [
        {
            "agency_id": a.id,
            "agency_name": a.name,
            "role": m.role,
            "is_owner": m.is_owner,
            "is_frozen": a.archived_at is not None,
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


# ── Архивация / восстановление / удаление навсегда (управление юзерами) ────────

def _owned_agencies(db: Session, user_id: int):
    """Агентства, где пользователь — владелец (is_owner), включая замороженные."""
    return [
        (m, a)
        for m, a in agency_membership_repo.list_for_user(db, user_id, include_archived=True)
        if m.is_owner
    ]


def archive_user(db: Session, user_id: int, *, freeze_agencies: bool = False) -> dict:
    """
    «Удалить» юзера → в архив. Аккаунт замораживается (is_active=False, archived_at),
    сессия сбрасывается (bump epoch — его выкидывает), Telegram/номер освобождаются
    (частичные уник. индексы) — при следующем входе человек заводит новый аккаунт.

    freeze_agencies=True — заодно замораживает агентства, где он владелец: сотрудники
    теряют к ним доступ, пока владельца не восстановят. False — агентства работают.
    """
    u = user_repo.get_by_id(db, user_id)
    if u is None or u.archived_at is not None:
        raise AppError("user_not_found_or_inactive", status.HTTP_404_NOT_FOUND)
    if u.role == "superadmin":
        raise AppError("cannot_archive_superadmin", status.HTTP_403_FORBIDDEN)

    now = datetime.now(timezone.utc)
    u.archived_at = now
    u.is_active = False
    u.session_epoch = (u.session_epoch or 0) + 1  # мгновенно рвём его сессии
    if freeze_agencies:
        for _m, a in _owned_agencies(db, u.id):
            if a.archived_at is None:
                a.archived_at = now
    db.commit()
    return get_platform_user(db, user_id)


def restore_user_data(db: Session, archived_user_id: int, target_user_id: int) -> None:
    """
    Восстановить данные архивного юзера, ПЕРЕДАВ их выбранному активному юзеру.
    Возвращаются ТОЛЬКО агентства, где архивный был владельцем — они «размораживаются»
    и переходят целевому (он становится владельцем). Роли пониже не возвращаются
    (перевступит по коду). После переноса архивная запись удаляется.
    """
    au = user_repo.get_by_id(db, archived_user_id)
    if au is None or au.archived_at is None:
        raise AppError("user_not_archived", status.HTTP_404_NOT_FOUND)
    target = user_repo.get_by_id(db, target_user_id)
    if target is None or target.archived_at is not None or target.role == "superadmin":
        raise AppError("archive_target_invalid", status.HTTP_400_BAD_REQUEST)

    owned = _owned_agencies(db, au.id)
    first_agency = None
    for m, a in owned:
        a.archived_at = None  # разморозить
        m.is_owner = False
        m.is_active = False
        tm = agency_membership_repo.get_or_create(
            db, user_id=target.id, agency_id=a.id,
            role="agency_admin", is_owner=True, is_active=True,
        )
        tm.is_owner = True
        tm.role = "agency_admin"
        tm.is_active = True
        if first_agency is None:
            first_agency = a

    # Если у целевого не было домашнего агентства (личный аккаунт) — делаем первым
    # восстановленным, чтобы приложение открывалось прямо в нём.
    if first_agency is not None and (target.agency_id is None or target.role == "user"):
        target.agency_id = first_agency.id
        target.role = "agency_admin"
        target.is_owner = True
    # Толкаем целевого перелогиниться, чтобы подтянулись новые членства.
    target.session_epoch = (target.session_epoch or 0) + 1

    # Архивную запись удаляем — данные перенесены (членства архивного каскадно уйдут).
    db.delete(au)
    db.commit()


def purge_user(db: Session, archived_user_id: int, *, actor=None) -> None:
    """
    Удалить архивного юзера НАВСЕГДА. Стирает и все агентства, где он был
    владельцем (со всеми объектами внутри). Агентства, где он был лишь сотрудником,
    НЕ трогаем — просто убираем его как сотрудника (членство уходит вместе с юзером).
    """
    au = user_repo.get_by_id(db, archived_user_id)
    if au is None or au.archived_at is None:
        raise AppError("user_not_archived", status.HTTP_404_NOT_FOUND)

    # Сначала — владельческие агентства целиком (delete_agency сам коммитит и чистит
    # фото/данные каскадом). Собираем id заранее: после удаления агентства членства
    # архивного в нём исчезают.
    from app.services import agency_service

    owned_ids = [a.id for _m, a in _owned_agencies(db, au.id)]
    for agency_id in owned_ids:
        agency_service.delete_agency(db, agency_id, actor=actor)

    # Затем — сам юзер (его членства в чужих агентствах уйдут каскадом; объекты,
    # что он добавлял в чужих агентствах, останутся — created_by обнулится SET NULL).
    au = user_repo.get_by_id(db, archived_user_id)
    if au is not None:
        db.delete(au)
        db.commit()
