"""
Схемы для справочника агентов агентства.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class AgentCreate(BaseModel):
    # Имя агента для отображения (например "Сарвар").
    name: str
    # Короткий код для генерации ID объектов (например "SAR"). 1–5 символов.
    code: str

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("agent_name_empty")
        return value

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        # Код приводим к верхнему регистру и убираем пробелы — так удобнее
        # и исключаем дубликаты вида "sar" / "SAR".
        value = value.strip().upper()
        if not value:
            raise ValueError("agent_code_empty")
        if len(value) > 5:
            raise ValueError("agent_code_too_long")
        if not value.isalnum():
            raise ValueError("agent_code_alnum")
        return value


class AgentUpdate(BaseModel):
    # Все поля необязательны — меняем только то, что прислали.
    name: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("agent_name_empty")
        return value


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    last_number: int
    is_active: bool
    created_at: datetime
