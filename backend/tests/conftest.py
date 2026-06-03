"""
Общая настройка для тестов с базой данных.

Тесты используют SQLite в памяти, чтобы не требовать PostgreSQL и проходить в
CI. В SQLite автоинкремент работает только у INTEGER PRIMARY KEY, а наши ключи —
BigInteger, поэтому здесь — правило компиляции BigInteger -> INTEGER ТОЛЬКО для
диалекта sqlite (на PostgreSQL в продакшене это не влияет).
"""
import pytest
from sqlalchemy import BigInteger, create_engine, event
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

    # ВКЛЮЧАЕМ проверку внешних ключей в SQLite (по умолчанию она ВЫКЛЮЧЕНА).
    # Без этого тесты не ловили бы ошибки целостности (например, удаление
    # объекта/агентства с фото) — а именно такие баги мы и чиним. С включённым
    # PRAGMA срабатывают и правила ON DELETE CASCADE/SET NULL из моделей.
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _rec):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
