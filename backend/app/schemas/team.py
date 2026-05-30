"""
Схемы управления командой агентства (просмотр сотрудников, вкл/выкл доступа).
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class MemberUpdate(BaseModel):
    # Пока разрешаем менять только активность (доступ) сотрудника.
    is_active: Optional[bool] = None
