"""
Бизнес-логика справочника агентов агентства.

Агентами управляет администратор агентства. Агент нужен для генерации
человекочитаемого ID объекта (код агента + порядковый номер).
"""
from typing import List

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models.agent import Agent
from app.repositories import agent_repo
from app.schemas.agent import AgentCreate, AgentUpdate


def list_agents(db: Session, agency_id: int, include_inactive: bool = False) -> List[Agent]:
    return agent_repo.get_all(db, agency_id, include_inactive=include_inactive)


def create_agent(db: Session, agency_id: int, payload: AgentCreate) -> Agent:
    # Код агента должен быть уникален в пределах агентства.
    existing = agent_repo.get_by_code(db, agency_id, payload.code)
    if existing is not None:
        raise AppError(
            "agent_code_exists", status.HTTP_409_CONFLICT, code=payload.code
        )
    agent = agent_repo.create(db, agency_id, name=payload.name, code=payload.code)
    db.commit()
    db.refresh(agent)
    return agent


def update_agent(
    db: Session, agency_id: int, agent_id: int, payload: AgentUpdate
) -> Agent:
    agent = agent_repo.get_by_id(db, agency_id, agent_id)
    if agent is None:
        raise AppError("agent_not_found", status.HTTP_404_NOT_FOUND)
    # Меняем только переданные поля (код не меняем — он влияет на уже выданные ID).
    if payload.name is not None:
        agent.name = payload.name
    if payload.is_active is not None:
        agent.is_active = payload.is_active
    db.commit()
    db.refresh(agent)
    return agent
