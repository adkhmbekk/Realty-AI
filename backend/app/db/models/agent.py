"""
Таблица "agents" — справочник агентов агентства.

Заменяет захардкоженные AGENT_CODES + agent_counters из старого бота.
Каждый агент принадлежит конкретному агентству (изоляция по agency_id) и
хранит короткий код (например "SAR") и счётчик последнего номера — из них
складывается человекочитаемый ID объекта (например "SAR-0001").

Генерация номера происходит атомарно (см. repositories/agent_repo.next_number):
    UPDATE agents SET last_number = last_number + 1 WHERE id = ... RETURNING last_number
— это исключает выдачу двух одинаковых ID при одновременном создании объектов.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Agent(Base):
    __tablename__ = "agents"
    # Код агента уникален в пределах агентства (а не глобально).
    __table_args__ = (
        UniqueConstraint("agency_id", "code", name="uq_agents_agency_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agencies.id"), nullable=False, index=True
    )
    # Имя агента для отображения (например "Сарвар").
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Короткий код для генерации ID объектов (например "SAR").
    code: Mapped[str] = mapped_column(String(5), nullable=False)
    # Счётчик последнего выданного номера (атомарно увеличивается).
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
