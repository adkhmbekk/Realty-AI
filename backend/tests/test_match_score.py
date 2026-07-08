"""
score_match (BL1): балл отражает КАЧЕСТВО совпадения — наличие цены и её близость
к бюджету, а не просто факт «прошёл фильтр». Раньше цена всегда давала полный балл.
"""
from types import SimpleNamespace

from app.services.client_service import score_match


def _req(**kw):
    base = dict(
        price_min=None, price_max=None, districts=None, types=None,
        rooms_min=None, rooms_max=None, floor_min=None, floor_max=None,
        land_area_min=None, land_area_max=None, area_min=None, area_max=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _apt(**kw):
    base = dict(price=None, rooms=None, area=None, floor=None, land_area=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_cheaper_scores_higher_within_budget():
    req = _req(price_min=40000, price_max=50000)
    cheap = score_match(_apt(price=40000), req)[0]
    pricey = score_match(_apt(price=50000), req)[0]
    assert cheap > pricey


def test_missing_price_loses_points():
    req = _req(price_min=40000, price_max=50000)
    with_price = score_match(_apt(price=45000), req)[0]
    without = score_match(_apt(price=None), req)[0]
    assert without < with_price


def test_missing_numeric_field_penalized():
    # Клиент указал комнаты, у объекта их нет → балл ниже полного.
    req = _req(rooms_min=2, rooms_max=3)
    assert score_match(_apt(rooms=None), req)[0] < 100
    assert score_match(_apt(rooms=2), req)[0] == 100
