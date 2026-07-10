"""
Сборка всех роутеров API под общим префиксом /api/v1.
"""
from fastapi import APIRouter

from app.api.routes import (
    agencies,
    apartments,
    auth,
    clients,
    dictionaries,
    exports,
    imports,
    invites,
    mls,
    photos,
    settings,
    sheets,
    superadmin,
    team,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(agencies.router)
api_router.include_router(settings.router)
api_router.include_router(invites.router)
api_router.include_router(team.router)
api_router.include_router(dictionaries.router)
api_router.include_router(apartments.router)
api_router.include_router(clients.router)
api_router.include_router(photos.router)
api_router.include_router(sheets.router)
api_router.include_router(imports.router)
api_router.include_router(exports.router)
api_router.include_router(mls.router)
api_router.include_router(superadmin.router)
