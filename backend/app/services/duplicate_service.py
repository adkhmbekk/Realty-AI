"""
Поиск возможных дубликатов объектов в базе агентства.

Зачем: массовый импорт (и ручное добавление) могут принести один и тот же
физический объект несколько раз — одну квартиру выкладывают разные агенты/
каналы. Жёсткой дедупликации при импорте по содержимому нет (она рискованна),
поэтому здесь даём «менеджер дубликатов»: группируем похожие объекты, а человек
решает — удалить лишние или подтвердить «не дубликаты».

Признак группировки (v1): НОМЕР ТЕЛЕФОНА собственника. Один номер — почти всегда
один и тот же объект/собственник. Нормализуем номер до последних 9 цифр
(убирает разнобой +998/998/0/пробелы/скобки). Подтверждённые «не дубликаты»
(duplicate_dismissals) больше не показываем.
"""
import re
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models.apartment import Apartment
from app.db.models.duplicate_dismissal import DuplicateDismissal
from app.services import apartment_service


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """Телефон → ключ группы (последние 9 цифр) или None, если непохоже на номер."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) < 7:
        return None
    return digits[-9:]


def find_duplicate_groups(db: Session, agency_id: int) -> List[dict]:
    """Группы возможных дубликатов (>=2 объекта с одним номером), кроме подтверждённых."""
    apts = (
        db.query(Apartment)
        .filter(
            Apartment.agency_id == agency_id,
            Apartment.deleted_at.is_(None),
            Apartment.owner_phone.isnot(None),
        )
        .order_by(Apartment.created_at.desc())
        .all()
    )
    by_key: dict = {}
    for a in apts:
        key = normalize_phone(a.owner_phone)
        if not key:
            continue
        by_key.setdefault(key, []).append(a)

    dismissed = {
        r[0]
        for r in db.query(DuplicateDismissal.group_key)
        .filter(DuplicateDismissal.agency_id == agency_id)
        .all()
    }

    groups: List[dict] = []
    for key, items in by_key.items():
        if len(items) < 2 or key in dismissed:
            continue
        apartment_service._attach_creators(db, items)
        groups.append(
            {"key": key, "phone": items[0].owner_phone, "count": len(items), "items": items}
        )
    # Самые «населённые» группы — сверху.
    groups.sort(key=lambda g: g["count"], reverse=True)
    return groups


def dismiss_group(db: Session, agency_id: int, key: str) -> None:
    """Отметить группу (по ключу) как «не дубликаты» — больше не показывать."""
    key = (key or "").strip()
    if not key:
        return
    exists = (
        db.query(DuplicateDismissal)
        .filter(
            DuplicateDismissal.agency_id == agency_id,
            DuplicateDismissal.group_key == key,
        )
        .first()
    )
    if exists is None:
        db.add(DuplicateDismissal(agency_id=agency_id, group_key=key))
        db.commit()
