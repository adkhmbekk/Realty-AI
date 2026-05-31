"""
Эндпоинты справочника агентов агентства.

Просмотр доступен любому сотруднику агентства (нужен для выбора агента при
создании объекта). Изменение справочника — только администратору агентства.
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_admin, require_agency_member
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.agent import AgentCreate, AgentOut, AgentUpdate
from app.services import agent_service

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=List[AgentOut])
def list_agents(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Список агентов своего агентства."""
    return agent_service.list_agents(
        db, current_user.agency_id, include_inactive=include_inactive
    )


@router.post("", response_model=AgentOut, status_code=201)
def create_agent(
    body: AgentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Добавить агента (имя + короткий код для генерации ID объектов)."""
    return agent_service.create_agent(db, current_user.agency_id, body)


@router.patch("/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: int,
    body: AgentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_admin),
):
    """Изменить агента (имя / активность). Код агента не меняется."""
    return agent_service.update_agent(db, current_user.agency_id, agent_id, body)
