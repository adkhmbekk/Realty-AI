"""
Приватность при импорте: телефоны собственника попадают ТОЛЬКО в owner_phone,
вырезаются из описания/адреса/названия; несколько номеров собираются (до 5) и
дедуплицируются; цена в описании НЕ принимается за телефон.
"""
from app.services.listing_import_service import _digits, _sanitize_phones


def test_phone_moved_out_of_description():
    out = _sanitize_phones({
        "owner_phone": None,
        "description": "Уютная квартира, свежий ремонт. Тел: +998 90 123-45-67",
        "address": None,
        "name": None,
    })
    assert out["owner_phone"] and _digits(out["owner_phone"]) == "998901234567"
    # В описании номера больше нет, полезный текст сохранён.
    assert "123" not in (out["description"] or "")
    assert "квартира" in out["description"]


def test_multiple_phones_collected_and_deduped():
    out = _sanitize_phones({
        "owner_phone": "+998901234567",
        "description": "Звоните: 998901234567 или 90 765 43 21",
        "address": None,
        "name": None,
    })
    nums = [_digits(x) for x in (out["owner_phone"] or "").split("\n")]
    assert "998901234567" in nums
    assert "907654321" in nums
    # Дубликат одного и того же номера не задваивается.
    assert nums.count("998901234567") == 1


def test_max_five_numbers():
    desc = "Тел: " + " ".join(f"+99890111{i:02d}22" for i in range(8))  # 8 разных номеров
    out = _sanitize_phones({"owner_phone": None, "description": desc, "address": None, "name": None})
    assert len((out["owner_phone"] or "").split("\n")) == 5


def test_price_is_not_treated_as_phone():
    out = _sanitize_phones({
        "owner_phone": None,
        "description": "Цена 1 200 000 сум, торг уместен.",
        "address": None,
        "name": None,
    })
    assert out["owner_phone"] is None
    # Цена осталась в описании.
    assert "1200000" in _digits(out["description"])
