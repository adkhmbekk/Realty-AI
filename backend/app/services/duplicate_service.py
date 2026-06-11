"""
Поиск возможных дубликатов объектов в базе агентства.

Зачем: массовый импорт (и ручное добавление) могут принести один и тот же
физический объект несколько раз — одну квартиру выкладывают разные агенты/
каналы. Жёсткой дедупликации при импорте по содержимому нет (она рискованна),
поэтому здесь даём «менеджер дубликатов»: группируем похожие объекты, а человек
решает — удалить лишние или подтвердить «не дубликаты».

Признак группировки (v3): СОВПАДЕНИЕ ФИКСИРОВАННЫХ ХАРАКТЕРИСТИК объекта —
район, комнаты, этаж, этажность, площадь, сотки. ТИП не участвует: разные
источники называют один объект по-разному (Дом/Участок/Земля…). ЦЕНА на
группировку не влияет: одинаковая или разная — дубликаты показываются в обоих
случаях (внутри группы цены и типы видны — человек выбирает, что оставить).
Свободные тексты (адрес, описание, телефон) не сравниваются — различаются от
площадки к площадке. Чтобы не плодить мусорные группы из полупустых карточек,
требуем минимум 3 заполненных характеристики.
Подтверждённые «не дубликаты» (duplicate_dismissals) больше не показываем.
"""
import re
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models.apartment import Apartment
from app.db.models.duplicate_dismissal import DuplicateDismissal
from app.services import apartment_service

# Минимум заполненных характеристик, чтобы объект участвовал в сравнении.
# Меньше — карточка слишком «пустая», совпадения были бы случайными.
_MIN_FILLED = 3


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """Телефон → последние 9 цифр (используется в импорте/поиске похожих)."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) < 7:
        return None
    return digits[-9:]


def _norm_text(v: Optional[str]) -> Optional[str]:
    """Строка → ключевая форма: без регистра и лишних пробелов."""
    if not v:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip().lower()
    return s or None


def _norm_num(v) -> Optional[str]:
    """Число → каноническая строка (70 и 70.0 — одно и то же)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return ("%g" % f)


def _group_key(a: Apartment) -> Optional[str]:
    """
    Ключ группы из фиксированных характеристик. ТИП не участвует: разные
    источники называют один объект по-разному (Дом/Участок/Земля и т.п.).
    ЦЕНА не участвует в сравнении: одинаковая она или разная — на группировку
    не влияет (дубликаты показываются в обоих случаях). None — объект слишком
    пустой, чтобы судить о дубликатах.
    """
    parts = [
        _norm_text(a.district),
        _norm_num(a.rooms),
        _norm_num(a.floor),
        _norm_num(a.total_floors),
        _norm_num(a.area),
        _norm_num(a.land_area),
    ]
    if sum(1 for p in parts if p is not None) < _MIN_FILLED:
        return None
    return "|".join(p if p is not None else "-" for p in parts)


def _group_label(a: Apartment) -> str:
    """Человекочитаемое описание группы для заголовка на экране.
    Тип не показываем — внутри группы он может различаться."""
    bits: List[str] = []
    if a.district:
        bits.append(str(a.district))
    if a.rooms is not None:
        bits.append(f"{a.rooms} комн.")
    if a.floor is not None and a.total_floors is not None:
        bits.append(f"{a.floor}/{a.total_floors} эт.")
    elif a.total_floors is not None:
        bits.append(f"{a.total_floors} эт.")
    if a.area is not None:
        bits.append(("%g" % float(a.area)) + " м²")
    if a.land_area is not None:
        bits.append(("%g" % float(a.land_area)) + " сот.")
    return " · ".join(bits)


def find_duplicate_groups(db: Session, agency_id: int) -> List[dict]:
    """Группы возможных дубликатов (>=2 объекта с одинаковыми фиксированными
    характеристиками), кроме подтверждённых «не дубликаты»."""
    apts = (
        db.query(Apartment)
        .filter(
            Apartment.agency_id == agency_id,
            Apartment.deleted_at.is_(None),
        )
        .order_by(Apartment.created_at.desc())
        .all()
    )
    by_key: dict = {}
    for a in apts:
        key = _group_key(a)
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
            {
                "key": key,
                "label": _group_label(items[0]),
                # phone оставлен для совместимости со старым фронтом; в v2 не используется.
                "phone": None,
                "count": len(items),
                "items": items,
            }
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
