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

# pool_pre_ping=True — проверять "живо" ли соединение перед использованием.
# pool_recycle — пересоздавать соединение раз в 30 мин (защита от «протухших»).
#
# statement_timeout=30s (M6): убивает ОТДЕЛЬНЫЙ SQL-запрос, если он выполняется
# дольше 30 секунд — защита от зависшего запроса, который держал бы соединение/
# воркер. Это безопасно: во время внешних вызовов (Telegram/Gemini/Playwright)
# SQL НЕ выполняется, поэтому фоновые операции таймаут не задевает.
#
# ВНИМАНИЕ (инцидент 2026-07): idle_in_transaction_session_timeout здесь СТАВИТЬ
# НЕЛЬЗЯ — он убивает соединение с ОТКРЫТОЙ простаивающей транзакцией (авто-импорт
# держит транзакцию во время внешних вызовов), после чего соединение возвращается
# в пул «отравленным» и валит пользовательские запросы. Вернём только после того,
# как внешние вызовы авто-импорта будут вынесены из транзакции.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={"options": "-c statement_timeout=30000"},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """Выдать сессию БД на один запрос и закрыть её после завершения."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
