"""
Доступ к данным агентов (таблица agents).

ВСЕ функции принимают agency_id и фильтруют по нему — это и есть изоляция
данных между агентствами на уровне репозитория (как требует ТЗ, раздел 6).
"""
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models.agent import Agent


def get_all(db: Session, agency_id: int, include_inactive: bool = False) -> List[Agent]:
    stmt = select(Agent).where(Agent.agency_id == agency_id)
    if not include_inactive:
        stmt = stmt.where(Agent.is_active.is_(True))
    stmt = stmt.order_by(Agent.name)
    return list(db.execute(stmt).scalars().all())


def get_by_id(db: Session, agency_id: int, agent_id: int) -> Optional[Agent]:
    # Обязательно фильтруем и по agency_id — нельзя достать чужого агента по id.
    return db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.agency_id == agency_id)
    ).scalar_one_or_none()


def get_by_code(db: Session, agency_id: int, code: str) -> Optional[Agent]:
    return db.execute(
        select(Agent).where(Agent.agency_id == agency_id, Agent.code == code)
    ).scalar_one_or_none()


def create(db: Session, agency_id: int, name: str, code: str) -> Agent:
    agent = Agent(agency_id=agency_id, name=name, code=code, last_number=0, is_active=True)
    db.add(agent)
    db.flush()  # чтобы получить сгенерированный id
    return agent


def next_number(db: Session, agency_id: int, agent_id: int) -> Optional[int]:
    """
    Атомарно увеличить счётчик агента и вернуть новый номер.

    Переносит логику generate_id из старого бота, но со строгой привязкой к
    агентству. Один SQL-оператор UPDATE ... RETURNING исключает гонки:
    два одновременных создания объектов получат разные номера.
    Возвращает None, если агент не найден в этом агентстве.
    """
    stmt = (
        update(Agent)
        .where(Agent.id == agent_id, Agent.agency_id == agency_id)
        .values(last_number=Agent.last_number + 1)
        .returning(Agent.last_number)
        # Нам нужно только возвращаемое число; не синхронизируем ORM-объекты
        # в сессии — так надёжнее и без лишнего запроса.
        .execution_options(synchronize_session=False)
    )
    return db.execute(stmt).scalar_one_or_none()
