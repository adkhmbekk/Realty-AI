"""
Бизнес-логика управления командой агентства.

Админ агентства видит своих сотрудников и может включать/отключать им доступ.
Всё строго в пределах своего агентства (изоляция по agency_id).
"""
from typing import List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models.user import User
from app.repositories import user_repo
from app.schemas.team import MemberUpdate


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

    # Защита от самоблокировки: админ не может отключить сам себя
    # (иначе агентство может остаться без управления).
    if member.id == current_user.id and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя отключить доступ самому себе.",
        )

    if payload.is_active is not None:
        member.is_active = payload.is_active

    db.commit()
    db.refresh(member)
    return member
