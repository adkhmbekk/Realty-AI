"""
Импортируем все модели здесь, чтобы SQLAlchemy "увидел" их все
(через Base.metadata) и смог создать соответствующие таблицы.
"""
from app.db.models.agency import Agency
from app.db.models.agency_sheet import AgencySheet
from app.db.models.apartment import Apartment
from app.db.models.apartment_event import ApartmentEvent
from app.db.models.apartment_photo import ApartmentPhoto
from app.db.models.audit_log import AuditLog
from app.db.models.dictionary import Dictionary
from app.db.models.duplicate_dismissal import DuplicateDismissal
from app.db.models.invite import Invite
from app.db.models.subscription_payment import SubscriptionPayment
from app.db.models.user import User

__all__ = [
    "Agency",
    "AgencySheet",
    "User",
    "Invite",
    "Dictionary",
    "Apartment",
    "ApartmentEvent",
    "ApartmentPhoto",
    "AuditLog",
    "SubscriptionPayment",
    "DuplicateDismissal",
]
