"""
Регресс-тесты для фикс-пакета по итогам глубокого ревью (2026-07):
  M1 — refresh-токен не принимается как access (type-confusion);
  M3 — личный аккаунт без агентства не тянет фото/шеринг общей базы (MLS);
  M4 — телефонный запрос в поиске пула не подтверждается по name (оракул).
"""
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.api.routes import mls as mls_routes
from app.core import security
from app.core.dependencies import get_current_user
from app.db.models.agency import Agency
from app.db.models.apartment import Apartment
from app.db.session import get_db
from app.repositories import apartment_repo, user_repo


def _app(db):
    app = FastAPI()
    app.include_router(mls_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db

    # Отдельный минимальный роут, чтобы проверить сам get_current_user на токенах.
    from app.db.models.user import User

    @app.get("/api/v1/whoami")
    def whoami(u: User = Depends(get_current_user)):
        return {"id": u.id}

    return TestClient(app, raise_server_exceptions=False)


def _agency(db, name="Alpha"):
    a = Agency(name=name, status="active", timezone="Asia/Tashkent", default_currency="USD")
    db.add(a)
    db.commit()
    return a


# ── M1: refresh-токен ≠ access ───────────────────────────────────────────────
def test_refresh_token_rejected_as_bearer(db):
    a = _agency(db)
    u = user_repo.create(db, telegram_id=1, role="agency_admin", agency_id=a.id)
    db.commit()
    client = _app(db)
    access = security.create_access_token({"user_id": u.id, "epoch": 0})
    refresh = security.create_refresh_token({"user_id": u.id, "epoch": 0})

    assert client.get("/api/v1/whoami", headers={"Authorization": f"Bearer {access}"}).status_code == 200
    # Refresh в Authorization должен отклоняться (иначе 30-дн токен = Bearer).
    r = client.get("/api/v1/whoami", headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 401


# ── M3: пул закрыт для аккаунта без агентства ────────────────────────────────
def test_pool_photos_forbidden_for_personal_account(db):
    a = _agency(db)
    owner = user_repo.create(db, telegram_id=2, role="agent", agency_id=a.id)
    apt = Apartment(agency_id=a.id, display_id="1", shared_mls=True, created_by=owner.id)
    db.add(apt)
    db.commit()
    client = _app(db)

    # role='user' без агентства — не член пула.
    personal = user_repo.create(db, telegram_id=3, role="user")
    db.commit()
    tok = security.create_access_token({"user_id": personal.id, "epoch": 0})
    r = client.get(f"/api/v1/mls/objects/{apt.id}/photos", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403

    # Член агентства — проходит (200/пустой список), не 403.
    tok2 = security.create_access_token({"user_id": owner.id, "epoch": 0})
    r2 = client.get(f"/api/v1/mls/objects/{apt.id}/photos", headers={"Authorization": f"Bearer {tok2}"})
    assert r2.status_code != 403


# ── M4: телефонный запрос не матчит name в пуле ──────────────────────────────
def test_pool_search_phone_query_does_not_match_name(db):
    a = _agency(db)
    u = user_repo.create(db, telegram_id=4, role="agent", agency_id=a.id)
    apt = Apartment(
        agency_id=a.id, display_id="1", shared_mls=True, status="active",
        created_by=u.id, name="Срочно 998901234567", district="Чиланзар", type="Квартира",
    )
    db.add(apt)
    db.commit()

    # Телефонный запрос (≥7 цифр) не должен находить объект по name (оракул закрыт).
    items, total = apartment_repo.list_mls_pool(db, q="998901234567")
    assert total == 0
    # Обычный текстовый поиск по name работает.
    items2, total2 = apartment_repo.list_mls_pool(db, q="Срочно")
    assert total2 == 1
    # Поиск по району (короткие/без цифр) — работает.
    items3, total3 = apartment_repo.list_mls_pool(db, q="Чиланзар")
    assert total3 == 1
