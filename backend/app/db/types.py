"""
Пользовательские типы колонок SQLAlchemy.

EncryptedText — текстовая колонка, которая ПРОЗРАЧНО шифруется при записи и
расшифровывается при чтении (см. app.core.crypto). Внешний код работает с обычной
строкой, а в базе лежит зашифрованное значение. Используется для Google
refresh-токенов (agency_sheets.refresh_token).
"""
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core import crypto


class EncryptedText(TypeDecorator):
    """Хранит строку в БД зашифрованной (Fernet), наружу отдаёт открытый текст."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        # перед записью в БД — зашифровать
        return crypto.encrypt(value)

    def process_result_value(self, value, dialect):
        # при чтении из БД — расшифровать
        return crypto.decrypt(value)
