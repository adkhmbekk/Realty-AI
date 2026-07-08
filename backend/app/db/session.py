"""
Подключение к базе данных.

- engine — "движок", который держит соединение с PostgreSQL.
- SessionLocal — фабрика сессий (одна сессия = один разговор с базой).
- get_db() — зависимость FastAPI: выдаёт сессию на время запроса и
  гарантированно закрывает её после.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# pool_pre_ping=True — проверять "живо" ли соединение перед использованием,
# чтобы не падать на разорванных соединениях.
# pool_recycle — пересоздавать соединение раз в 30 мин (защита от «протухших»).
# statement_timeout / idle_in_transaction_session_timeout (M6): ни один запрос
# и ни одна «зависшая» транзакция не держат соединение бесконечно — иначе
# несколько плохих запросов исчерпали бы пул и подвесили приложение.
# connect_args с options — Postgres-специфичны; тесты используют отдельный
# SQLite-движок (см. conftest), их это не касается.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=10,
    max_overflow=20,
    pool_timeout=10,
    connect_args={
        "options": "-c statement_timeout=15000 -c idle_in_transaction_session_timeout=15000",
    },
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """Выдать сессию БД на один запрос и закрыть её после завершения."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
