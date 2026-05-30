"""
Базовый класс для всех моделей базы данных (таблиц).

В SQLAlchemy каждая таблица описывается классом, который наследуется от Base.
Через Base.metadata система знает обо всех таблицах и умеет их создавать.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
