"""
Бизнес-логика управления командой агентства.

Админ агентства видит своих сотрудников, может включать/отключать им доступ,
менять роль (агент ↔ администратор агентства), передавать роль главного и
исключать сотрудников из агентства. Всё строго в пределах своего агентства
(изоляция по agency_id). Значимые действия пишутся в журнал аудита.
"""
from typing import List, Optional

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models.user import User
from app.repositories import audit_repo, user_repo
from app.schemas.team import MemberUpdate

# Роли, которые сотруднику можно назначить внутри агентства.
ASSIGNABLE_ROLES = ("agency_admin", "agent")


def _name(u: Optional[User]) -> Optional[str]:
    if u is None:
        return None
    if u.full_name:
        return u.full_name
    if u.username:
        return "@" + u.username
    return f"ID {u.telegram_id}"


def _audit(db: Session, actor: User, action: str, member: User, note: Optional[str] = None) -> None:
    audit_repo.add(
        db,
        action=action,
        agency_id=actor.agency_id,
        actor_user_id=actor.id,
        actor_telegram_id=actor.telegram_id,
        actor_name=_name(actor),
        target=_name(member),
        note=note,
    )


def list_members(db: Session, agency_id: int) -> List[User]:
    return user_repo.get_by_agency(db, agency_id)


def update_member(
    db: Session,
    agency_id: int,
    current_user: User,
    member_id: int,
    payload: MemberUpdate,
) -> User:
    member = user_repo.get_member(db, agency_id, member_id)
    if member is None:
        raise AppError("member_not_found", status.HTTP_404_NOT_FOUND)

    is_self = member.id == current_user.id

    # Защита от самоблокировки: админ не может отключить сам себя.
    if is_self and payload.is_active is False:
        raise AppError("cannot_disable_self", status.HTTP_400_BAD_REQUEST)

    # Иерархия админов: действия над администратором агентства доступны только
    # ГЛАВНОМУ админу (is_owner).
    if member.role == "agency_admin" and not is_self and not current_user.is_owner:
        raise AppError("only_owner_manage_admins", status.HTTP_403_FORBIDDEN)
    # Главного администратора нельзя изменить через раздел «Команда».
    if member.is_owner and not is_self:
        raise AppError("cannot_change_owner", status.HTTP_403_FORBIDDEN)

    if payload.role is not None:
        new_role = payload.role
        if new_role not in ASSIGNABLE_ROLES:
            raise AppError("invalid_role", status.HTTP_400_BAD_REQUEST)
        # Менять роли может только главный администратор агентства.
        if new_role != member.role and not current_user.is_owner:
            raise AppError("only_owner_change_roles", status.HTTP_403_FORBIDDEN)
        # Админ не может понизить сам себя.
        if is_self and new_role != member.role:
            raise AppError("cannot_change_own_role", status.HTTP_400_BAD_REQUEST)
        if new_role != member.role:
            member.role = new_role
            _audit(db, current_user, "member_role_changed", member, note=new_role)

    if payload.is_active is not None and payload.is_active != member.is_active:
        member.is_active = payload.is_active
        _audit(
            db, current_user,
            "member_enabled" if payload.is_active else "member_disabled", member,
        )

    db.commit()
    db.refresh(member)
    return member


def remove_member(
    db: Session, agency_id: int, current_user: User, member_id: int
) -> None:
    """
    Полностью исключить сотрудника из агентства: отвязать от агентства
    (agency_id = NULL) и сбросить роль/флаги. После этого человек может
    вступить в другое агентство по приглашению (раньше он навсегда «прилипал»
    к одному агентству, даже будучи отключённым).

    Исключать сотрудников может только ГЛАВНЫЙ администратор. Себя и другого
    главного исключить нельзя.
    """
    if not current_user.is_owner:
        raise AppError("only_owner_manage_admins", status.HTTP_403_FORBIDDEN)

    member = user_repo.get_member(db, agency_id, member_id)
    if member is None:
        raise AppError("member_not_found", status.HTTP_404_NOT_FOUND)
    if member.id == current_user.id:
        raise AppError("cannot_remove_self", status.HTTP_400_BAD_REQUEST)
    if member.is_owner:
        raise AppError("cannot_change_owner", status.HTTP_403_FORBIDDEN)

    _audit(db, current_user, "member_removed", member)
    member.agency_id = None
    member.role = "agent"
    member.is_owner = False
    member.is_active = False
    db.commit()


def transfer_ownership(
    db: Session, agency_id: int, current_user: User, member_id: int
) -> User:
    """
    Передать роль главного администратора другому сотруднику.
    Делать это может только текущий главный админ.
    """
    if not current_user.is_owner:
        raise AppError("only_owner_transfer", status.HTTP_403_FORBIDDEN)

    member = user_repo.get_member(db, agency_id, member_id)
    if member is None:
        raise AppError("member_not_found", status.HTTP_404_NOT_FOUND)
    if member.id == current_user.id:
        raise AppError("already_owner", status.HTTP_400_BAD_REQUEST)

    member.role = "agency_admin"
    member.is_active = True
    member.is_owner = True
    current_user.is_owner = False

    _audit(db, current_user, "owner_transferred", member)

    db.commit()
    db.refresh(member)
    return member


def list_audit(db: Session, agency_id: int) -> list:
    """Журнал действий по своему агентству (для администратора агентства)."""
    return audit_repo.list_for_agency(db, agency_id)
