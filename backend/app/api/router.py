"""
Сборка всех роутеров API под общим префиксом /api/v1.
"""
from fastapi import APIRouter

from app.api.routes import agencies, auth

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(agencies.router)
