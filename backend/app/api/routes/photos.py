"""
Эндпоинты фотографий объектов.

- список / загрузка с устройства / импорт из Telegram / удаление — для
  сотрудника агентства (изоляция по agency_id);
- отдача самого файла — публичная (по неугадываемому ключу), чтобы тег <img>
  мог показать картинку без заголовка авторизации.
"""
from typing import List

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_member
from app.db.models.user import User
from app.db.session import get_db
from app.services import photo_service

router = APIRouter(tags=["photos"])


@router.get("/apartments/{apartment_id}/photos")
def list_photos(
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Список фотографий объекта (метаданные + ссылки)."""
    return photo_service.list_photos(db, current_user.agency_id, apartment_id)


@router.post("/apartments/{apartment_id}/photos", status_code=201)
async def upload_photos(
    apartment_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Загрузить одно или несколько фото с устройства."""
    blobs = []
    for f in files:
        data = await f.read()
        blobs.append((data, f.content_type or "image/jpeg"))
    return photo_service.add_blobs(db, current_user.agency_id, apartment_id, blobs)


@router.post("/apartments/{apartment_id}/photos/import-telegram", status_code=201)
def import_telegram(
    apartment_id: int,
    url: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Импортировать все фото из поста открытого Telegram-канала по ссылке."""
    return photo_service.import_from_telegram(db, current_user.agency_id, apartment_id, url)


@router.delete("/apartments/{apartment_id}/photos/{photo_id}", status_code=204)
def delete_photo(
    apartment_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Удалить конкретное фото объекта."""
    photo_service.delete_photo(db, current_user.agency_id, apartment_id, photo_id)


@router.get("/photos/{key}")
def serve_photo(key: str, db: Session = Depends(get_db)):
    """Публичная отдача файла по ключу (для тега <img>)."""
    found = photo_service.file_for(db, key)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Фото не найдено.")
    path, content_type = found
    return FileResponse(path, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})
