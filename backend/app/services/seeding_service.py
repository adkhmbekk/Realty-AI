"""
Наполнение нового агентства значениями по умолчанию.

Вызывается при создании агентства, чтобы оно сразу было готово к работе:
есть районы, типы недвижимости и запасной агент для генерации ID.

Функция НЕ делает commit — она работает внутри той же транзакции, что и
создание агентства (commit делает вызывающий код).
"""
from sqlalchemy.orm import Session

from app.core.defaults import (
    DEFAULT_AGENT_CODE,
    DEFAULT_AGENT_NAME,
    DEFAULT_DISTRICTS,
    DEFAULT_PROPERTY_TYPES,
)
from app.repositories import agent_repo, dictionary_repo


def seed_agency_defaults(db: Session, agency_id: int) -> None:
    # Районы (с сохранением порядка из списка).
    for order, district in enumerate(DEFAULT_DISTRICTS):
        dictionary_repo.create(
            db, agency_id, category="district", value=district, sort_order=order
        )

    # Типы недвижимости.
    for order, prop_type in enumerate(DEFAULT_PROPERTY_TYPES):
        dictionary_repo.create(
            db, agency_id, category="property_type", value=prop_type, sort_order=order
        )

    # Запасной агент «Другое» (код OTH) — чтобы можно было создавать объекты
    # сразу, ещё до того как админ заведёт своих агентов.
    agent_repo.create(db, agency_id, name=DEFAULT_AGENT_NAME, code=DEFAULT_AGENT_CODE)
