"""
BL2: кадастровые/документные номера НЕ должны приниматься за телефон и вырезаться
из описания. Телефонная группировка дефисами (городской номер) — по-прежнему да.
"""
from app.services.listing_import_service import _digits, _is_phone, _sanitize_phones


def test_cadastral_not_phone():
    raw = "12-34-567-89-01"  # 4 группы, 11 цифр — кадастр, не телефон
    assert _is_phone(raw, _digits(raw), "", lenient=False) is False


def test_landline_with_dashes_is_phone():
    raw = "71-234-56-78"  # 3 группы, 9 цифр — городской номер
    assert _is_phone(raw, _digits(raw), "", lenient=False) is True


def test_sanitize_keeps_cadastral_in_description():
    out = {"description": "Кадастр 12-34-567-89-01, срочно", "owner_phone": None}
    res = _sanitize_phones(out)
    assert "12-34-567-89-01" in (res["description"] or "")
    assert res["owner_phone"] is None
