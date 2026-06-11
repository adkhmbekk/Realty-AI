"""
Таблица "duplicate_dismissals" — группы объектов, которые пользователь ПОДТВЕРДИЛ
как «не дубликаты» (чтобы они больше не показывались в менеджере дубликатов).

group_key — устойчивый ключ группы (нормализованный телефон собственника:
последние 9 цифр). Один ключ на агентство.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DuplicateDismissal(Base):
    __tablename__ = "duplicate_dismissals"
    __table_args__ = (
        UniqueConstraint("agency_id", "group_key", name="uq_dup_dismissal_agency_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group_key: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
