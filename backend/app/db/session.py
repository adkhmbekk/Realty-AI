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
engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """Выдать сессию БД на один запрос и закрыть её после завершения."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
