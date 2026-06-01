"""
Схемы для гибких справочников агентства (районы, типы и т.д.).
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class DictionaryCreate(BaseModel):
    # Категория справочника: district / property_type / condition / ...
    category: str
    # Значение (например "Чиланзарский").
    value: str
    sort_order: int = 0

    @field_validator("category", "value")
    @classmethod
    def _not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Значение не может быть пустым.")
        return value


class DictionaryUpdate(BaseModel):
    value: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator("value")
    @classmethod
    def _value_not_empty(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Значение не может быть пустым.")
        return value


class DictionaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    value: str
    sort_order: int
    is_active: bool
