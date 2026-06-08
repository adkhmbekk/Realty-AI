"""
Эндпоинты фотографий объектов.

- список / загрузка с устройства / импорт из Telegram / удаление — для
  сотрудника агентства (изоляция по agency_id);
- отдача самого файла — публичная (по неугадываемому ключу), чтобы тег <img>
  мог показать картинку без заголовка авторизации.

Загрузка с устройства принимает фото как JSON (base64/data-URL), а НЕ как
multipart/form-data: обычные JSON-запросы стабильно проходят через туннель,
а multipart с файлом — нет.
"""
from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, conlist, constr
from sqlalchemy.orm import Session

from app.core.dependencies import require_agency_member
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.apartment import PhotoImportUrlsIn
from app.services import photo_service

router = APIRouter(tags=["photos"])

# Допустимые типы для безопасной отдачи файла как изображения. Всё остальное
# отдаём как «скачиваемый» поток (attachment) — чтобы браузер НЕ интерпретировал
# содержимое как HTML/SVG со скриптом (защита от Stored XSS).
_SAFE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Ограничения на входной JSON с фото (защита от чрезмерного расхода памяти):
#   - не более MAX_PHOTOS изображений за один запрос;
#   - каждая строка base64/data-URL — не длиннее ~15 МБ в бинарном виде.
_MAX_IMAGE_CHARS = 20_000_000


class PhotoUploadIn(BaseModel):
    # Изображения как data-URL ("data:image/jpeg;base64,...") или чистый base64.
    images: conlist(
        constr(max_length=_MAX_IMAGE_CHARS),
        min_length=1,
        max_length=photo_service.MAX_PHOTOS,
    )


@router.get("/apartments/{apartment_id}/photos")
def list_photos(
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Список фотографий объекта (метаданные + ссылки)."""
    return photo_service.list_photos(db, current_user.agency_id, apartment_id)


@router.post(
    "/apartments/{apartment_id}/photos",
    status_code=201,
    dependencies=[Depends(rate_limit(30, 60, "photo_upload"))],
)
def upload_photos(
    apartment_id: int,
    body: PhotoUploadIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Загрузить фото с устройства (передаются как base64 в JSON)."""
    blobs = []
    for s in body.images:
        data, ctype = photo_service.decode_data_url(s)
        if data:
            blobs.append((data, ctype))
    if not blobs:
        raise AppError("no_photos_to_upload", status.HTTP_400_BAD_REQUEST)
    return photo_service.add_blobs(db, current_user.agency_id, apartment_id, blobs)


@router.post(
    "/apartments/{apartment_id}/photos/import-telegram",
    status_code=201,
    dependencies=[Depends(rate_limit(20, 60, "photo_import"))],
)
async def import_telegram(
    apartment_id: int,
    url: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Импортировать все фото из поста открытого Telegram-канала по ссылке."""
    return await photo_service.import_from_telegram(db, current_user.agency_id, apartment_id, url)


@router.post(
    "/apartments/{apartment_id}/photos/import-urls",
    status_code=201,
    dependencies=[Depends(rate_limit(20, 60, "photo_import_urls"))],
)
async def import_photo_urls(
    apartment_id: int,
    body: PhotoImportUrlsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_agency_member),
):
    """Прикрепить фото по прямым ссылкам на изображения (из импорта объявления)."""
    return await photo_service.import_from_image_urls(
        db, current_user.agency_id, apartment_id, body.urls
    )


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
        raise AppError("photo_not_found", status.HTTP_404_NOT_FOUND)
    path, content_type = found

    # Безопасная отдача: запрещаем браузеру «угадывать» тип (nosniff). Если тип
    # не входит в белый список изображений (например, оставшийся с прошлых
    # версий SVG), отдаём как вложение-поток, чтобы содержимое НЕ исполнялось
    # как HTML/скрипт в нашем домене (защита от Stored XSS).
    headers = {
        "Cache-Control": "public, max-age=86400",
        "X-Content-Type-Options": "nosniff",
    }
    if content_type in _SAFE_IMAGE_TYPES:
        headers["Content-Disposition"] = "inline"
        media_type = content_type
    else:
        headers["Content-Disposition"] = "attachment; filename=download"
        media_type = "application/octet-stream"
    return FileResponse(path, media_type=media_type, headers=headers)
