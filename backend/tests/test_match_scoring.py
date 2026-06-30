"""Волна 1 «Умный подбор»: балл совпадения, причины, «мягкий» режим, площадь.

Чистые функции без БД: apartment_matches_request (предикат подбора) и
score_match (балл 0-100 + причины {good, missing}).
"""
from types import SimpleNamespace

from app.services.client_service import apartment_matches_request, score_match


def _apt(**kw):
    base = dict(
        deal_type="sale", type=None, district=None, rooms=None, floor=None,
        area=None, land_area=None, currency="USD", price=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _req(**kw):
    base = dict(
        deal_type="sale", types=None, districts=None, rooms_min=None, rooms_max=None,
        floor_min=None, floor_max=None, area_min=None, area_max=None,
        land_area_min=None, land_area_max=None, currency=None, price_min=None, price_max=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_score_full_match_is_100():
    req = _req(price_max=60000, districts=["Юнусабад"], rooms_min=2)
    apt = _apt(price=50000, currency="USD", district="Юнусабад", rooms=3)
    assert apartment_matches_request(apt, req) is True
    score, reasons = score_match(apt, req)
    assert score == 100
    assert "price" in reasons["good"]
    assert "district" in reasons["good"]
    assert "rooms" in reasons["good"]
    assert reasons["missing"] == []


def test_missing_field_is_flagged_not_excluded():
    # Клиент указал этаж, но у объекта он не заполнен → объект ВСЁ РАВНО подходит,
    # но помечается «данные неполные», и балл ниже 100.
    req = _req(price_max=60000, floor_min=2)
    apt = _apt(price=50000, currency="USD", floor=None)
    assert apartment_matches_request(apt, req) is True
    score, reasons = score_match(apt, req)
    assert "floor" in reasons["missing"]
    assert score < 100


def test_present_field_out_of_range_excluded():
    # Если поле заполнено и вышло за рамки — отсекаем (это не «неполные данные»).
    req = _req(rooms_min=3)
    assert apartment_matches_request(_apt(rooms=2), req) is False
    assert apartment_matches_request(_apt(rooms=4), req) is True


def test_area_filter_in_out_and_missing():
    req = _req(area_min=80, area_max=120)
    assert apartment_matches_request(_apt(area=100), req) is True
    assert apartment_matches_request(_apt(area=50), req) is False
    # Площадь у объекта не указана → мягкий режим: не отсекаем.
    assert apartment_matches_request(_apt(area=None), req) is True


def test_budget_is_hard_even_when_price_missing():
    # Бюджет жёсткий (выбор пользователя): объект без цены не проходит.
    req = _req(price_max=60000)
    assert apartment_matches_request(_apt(price=None), req) is False
    assert apartment_matches_request(_apt(price=50000, currency="USD"), req) is True


def test_score_no_criteria_is_100():
    # Пустых заявок не бывает (валидируется выше), но функция должна быть устойчива.
    score, reasons = score_match(_apt(), _req())
    assert score == 100
    assert reasons == {"good": [], "missing": []}
