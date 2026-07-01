"""Удаление ошибочной записи о платеже агентства (agency_service.delete_payment)."""
from decimal import Decimal

import pytest

from app.core.errors import AppError
from app.db.models.agency import Agency
from app.repositories import payment_repo
from app.services import agency_service


def _agency(db, name="Pay"):
    ag = Agency(name=name, status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(ag)
    db.commit()
    return ag


def test_delete_payment(db):
    a = _agency(db)
    p = payment_repo.add(db, agency_id=a.id, action="extend", amount=Decimal("100"), currency="USD")
    db.commit()
    assert len(agency_service.list_payments(db, a.id)) == 1
    agency_service.delete_payment(db, a.id, p.id)
    assert len(agency_service.list_payments(db, a.id)) == 0
    with pytest.raises(AppError):
        agency_service.delete_payment(db, a.id, p.id)  # уже удалён


def test_delete_payment_cross_agency_blocked(db):
    a = _agency(db, "A")
    b = _agency(db, "B")
    p = payment_repo.add(db, agency_id=a.id, action="extend", amount=Decimal("50"), currency="USD")
    db.commit()
    with pytest.raises(AppError):
        agency_service.delete_payment(db, b.id, p.id)  # чужой платёж — нельзя
    assert len(agency_service.list_payments(db, a.id)) == 1
