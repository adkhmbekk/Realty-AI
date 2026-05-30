"""
Импортируем все модели здесь, чтобы SQLAlchemy "увидел" их все
(через Base.metadata) и смог создать соответствующие таблицы.
"""
from app.db.models.agency import Agency
from app.db.models.invite import Invite
from app.db.models.user import User

__all__ = ["Agency", "User", "Invite"]
