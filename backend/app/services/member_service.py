"""
Бизнес-логика управления командой агентства.

Админ агентства видит своих сотрудников, может включать/отключать им доступ
и менять роль (агент ↔ администратор агентства).
Всё строго в пределах своего агентства (изоляция по agency_id).
"""
from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.user import User
from app.repositories import user_repo
from app.schemas.team import MemberUpdate

# Роли, которые сотруднику можно назначить внутри агентства.
ASSIGNABLE_ROLES = ("agency_admin", "agent")


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Сотрудник не найден."
        )

    is_self = member.id == current_user.id

    # Защита от самоблокировки: админ не может отключить сам себя
    # (иначе агентство может остаться без управления).
    if is_self and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя отключить доступ самому себе.",
        )

    # Иерархия админов: действия над администратором агентства (понизить,
    # отключить) доступны только ГЛАВНОМУ админу (is_owner). Повышенный из агента
    # админ не может действовать против других админов и тех, кто его повысил.
    if member.role == "agency_admin" and not is_self and not current_user.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Управлять администраторами может только главный администратор агентства.",
        )
    # Главного администратора нельзя изменить через раздел «Команда».
    if member.is_owner and not is_self:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Главного администратора агентства изменить нельзя.",
        )

    if payload.role is not None:
        new_role = payload.role
        if new_role not in ASSIGNABLE_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Недопустимая роль. Доступно: администратор агентства или агент.",
            )
        # Защита: админ не может понизить сам себя — иначе агентство рискует
        # остаться без администратора. Сменить свою роль может только другой админ.
        if is_self and new_role != member.role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя менять роль самому себе. Попросите другого администратора.",
            )
        member.role = new_role

    if payload.is_active is not None:
        member.is_active = payload.is_active

    db.commit()
    db.refresh(member)
    return member
