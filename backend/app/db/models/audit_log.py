"""
Таблица "audit_log" — общий журнал значимых действий в системе.

В отличие от apartment_events (действия только над объектами недвижимости),
сюда пишутся ВСЕ важные события: вход, выдача/отзыв/использование приглашений,
смена ролей, включение/отключение и исключение сотрудников, создание/удаление/
переименование агентств, смена администратора и изменение подписки.

Зачем: прозрачность и доказуемость. При споре «кто удалил объект / кто меня
разжаловал / когда продлили подписку» в журнале есть ответ. Для системы с
персональными данными (телефоны) журнал аудита — ещё и требование безопасности.

agency_id может быть NULL — например, действие суперадмина до того, как
агентство создано (но обычно проставляется id затронутого агентства).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        # Быстрая выборка журнала конкретного агентства (свежие сверху).
        Index("ix_audit_log_agency_created", "agency_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Затронутое агентство (NULL — действие вне контекста агентства).
    # FK не ставим намеренно: журнал должен переживать удаление агентства.
    agency_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    # Кто совершил действие. FK тоже не ставим — запись должна сохраняться,
    # даже если пользователь позже удалён/исключён.
    actor_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    actor_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # Имя автора на момент действия (чтобы не делать join при показе журнала).
    actor_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # IP-адрес источника действия (например, при входе) — для разбора инцидентов (L8).
    ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Машиночитаемый код действия (login / invite_created / member_role_changed / ...).
    action: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # На что направлено действие (например, имя/ID сотрудника, № объекта).
    target: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Человекочитаемые детали (свободный текст).
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
