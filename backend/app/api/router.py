"""
Сборка всех роутеров API под общим префиксом /api/v1.
"""
from fastapi import APIRouter

from app.api.routes import agencies, agents, apartments, auth, dictionaries

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(agencies.router)
api_router.include_router(agents.router)
api_router.include_router(dictionaries.router)
api_router.include_router(apartments.router)
