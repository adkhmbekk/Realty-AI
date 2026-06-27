"""Аренда: распознавание типа сделки ИИ-очисткой и защита подбора от кросс-типа.

Чистые функции (без БД и сети): _clean (пост-обработка ответа ИИ) и
apartment_matches_request (предикат подбора объект↔заявка).
"""
from types import SimpleNamespace

from app.services.listing_import_service import _clean
from app.services.client_service import apartment_matches_request


# ── _clean: тип сделки и срок аренды ─────────────────────────────────
def test_clean_defaults_to_sale():
    out = _clean({"type": "Квартира", "price": 50000})
    assert out["deal_type"] == "sale"
    assert out["rent_period"] is None


def test_clean_rent_keeps_period():
    out = _clean({"type": "Квартира", "price": 400, "deal_type": "rent", "rent_period": "month"})
    assert out["deal_type"] == "rent"
    assert out["rent_period"] == "month"


def test_clean_rent_day():
    out = _clean({"deal_type": "rent", "rent_period": "day", "price": 40})
    assert out["deal_type"] == "rent" and out["rent_period"] == "day"


def test_clean_rent_bad_period_falls_back_to_month():
    out = _clean({"deal_type": "rent", "rent_period": "weird"})
    assert out["rent_period"] == "month"


def test_clean_sale_ignores_stray_period():
    # У продажи срока аренды быть не должно даже если модель его вернула.
    out = _clean({"deal_type": "sale", "rent_period": "day"})
    assert out["rent_period"] is None


# ── Подбор: продажа и аренда не должны смешиваться ───────────────────
def _apt(**kw):
    base = dict(deal_type="sale", type=None, district=None, rooms=None, floor=None,
                land_area=None, currency="USD", price=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _req(**kw):
    base = dict(deal_type="sale", types=None, districts=None, rooms_min=None, rooms_max=None,
                floor_min=None, floor_max=None, land_area_min=None, land_area_max=None,
                currency=None, price_min=None, price_max=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_buyer_request_does_not_match_rental():
    # Покупатель (sale) с большим бюджетом НЕ должен ловить дешёвую аренду.
    req = _req(deal_type="sale", price_max=60000)
    rental = _apt(deal_type="rent", price=500, currency="USD")
    assert apartment_matches_request(rental, req) is False


def test_renter_request_does_not_match_sale():
    req = _req(deal_type="rent", price_max=1000)
    sale = _apt(deal_type="sale", price=50000, currency="USD")
    assert apartment_matches_request(sale, req) is False


def test_rent_matches_rent():
    req = _req(deal_type="rent", price_max=1000, currency="USD")
    rental = _apt(deal_type="rent", price=500, currency="USD")
    assert apartment_matches_request(rental, req) is True


def test_sale_matches_sale_by_default():
    # Старые заявки/объекты без явного типа считаются продажей и подбираются.
    req = _req(deal_type="sale")
    sale = _apt(deal_type="sale", type="Квартира")
    assert apartment_matches_request(sale, req) is True
