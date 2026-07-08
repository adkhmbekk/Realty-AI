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
#
# ВНИМАНИЕ (инцидент 2026-07): idle_in_transaction_session_timeout здесь СТАВИТЬ
# НЕЛЬЗЯ. Некоторые фоновые операции (авто-импорт Telegram) держат транзакцию
# открытой во время долгих внешних вызовов; серверный таймаут убивал такое
# соединение, оно возвращалось в пул «отравленным» и валило пользовательские
# запросы (вход в агентство, общая база). statement_timeout тоже убрали до
# отдельной аккуратной проработки (сначала — вынести внешние вызовы из транзакций).
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=1800)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """Выдать сессию БД на один запрос и закрыть её после завершения."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
