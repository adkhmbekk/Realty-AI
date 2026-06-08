"""
Сборка всех роутеров API под общим префиксом /api/v1.
"""
from fastapi import APIRouter

from app.api.routes import (
    agencies,
    apartments,
    auth,
    dictionaries,
    invites,
    photos,
    settings,
    sheets,
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
api_router.include_router(photos.router)
api_router.include_router(sheets.router)
