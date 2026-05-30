"""
Схемы для агентств.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class AgencyCreate(BaseModel):
    name: str
    # Telegram ID человека, который станет админом этого агентства.
    admin_telegram_id: int
    admin_username: Optional[str] = None
    # На сколько дней открыть подписку при создании.
    subscription_days: int = 30


class AgencySubscriptionUpdate(BaseModel):
    # extend — продлить на N дней (и сделать активной);
    # freeze — заморозить; activate — снова активировать.
    action: Literal["extend", "freeze", "activate"]
    days: Optional[int] = 30


class AgencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    subscription_expires_at: Optional[datetime] = None
    created_at: datetime
