"""
Общая настройка для тестов с базой данных.

Тесты используют SQLite в памяти, чтобы не требовать PostgreSQL и проходить в
CI. В SQLite автоинкремент работает только у INTEGER PRIMARY KEY, а наши ключи —
BigInteger, поэтому здесь — правило компиляции BigInteger -> INTEGER ТОЛЬКО для
диалекта sqlite (на PostgreSQL в продакшене это не влияет).
"""
import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models  # noqa: F401  — регистрирует все модели
from app.db.base import Base


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(type_, compiler, **kw):  # noqa: ANN001
    return "INTEGER"


@pytest.fixture()
def db():
    """Чистая БД SQLite в памяти на каждый тест (общая на все соединения)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
