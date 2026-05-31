"""
Бизнес-логика фотографий объектов.

Файлы хранятся на диске (в папке settings.photos_dir, смонтированной на
Docker-том), а метаданные — в таблице apartment_photos. Публичная ссылка вида
/api/v1/photos/<ключ> отдаёт сам файл (ключ случайный и неугадываемый).

Поддерживаются:
  - загрузка файлов с устройства (add_blobs);
  - импорт всех фото из поста открытого Telegram-канала по ссылке;
  - выборочное удаление фото;
  - синхронизация «обложки» (apartment.photo_url = первое фото) — чтобы фото
    показывалось в списке и в карточке для отправки.
"""
import html as html_lib
import os
import re
import secrets
import urllib.request
from typing import List, Optional, Tuple

from fastapi import HTTPException, status

from app.config import settings
from app.repositories import apartment_photo_repo, apartment_repo

MAX_PHOTOS = 20
MAX_BYTES = 12 * 1024 * 1024  # 12 МБ на файл
MAX_HTML_BYTES = 4 * 1024 * 1024
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def _ensure_dir() -> None:
    os.makedirs(settings.photos_dir, exist_ok=True)


def _path(key: str) -> str:
    return os.path.join(settings.photos_dir, key)


def public_url(key: str) -> str:
    return f"/api/v1/photos/{key}"


def to_out(photo) -> dict:
    return {"id": photo.id, "url": public_url(photo.storage_key), "sort_order": photo.sort_order}


def _require_apartment(db, agency_id: int, apartment_id: int):
    apt = apartment_repo.get_by_id(db, agency_id, apartment_id)
    if apt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Объект не найден.")
    return apt


def _sync_cover(db, agency_id: int, apartment_id: int) -> None:
    """Обложкой объекта делаем первое фото (или очищаем, если фото нет)."""
    apt = apartment_repo.get_by_id(db, agency_id, apartment_id)
    if apt is None:
        return
    photos = apartment_photo_repo.list_for(db, agency_id, apartment_id)
    apt.photo_url = public_url(photos[0].storage_key) if photos else None


def list_photos(db, agency_id: int, apartment_id: int) -> List[dict]:
    _require_apartment(db, agency_id, apartment_id)
    return [to_out(p) for p in apartment_photo_repo.list_for(db, agency_id, apartment_id)]


def _save_one(db, agency_id: int, apartment_id: int, data: bytes, content_type: str, order: int):
    _ensure_dir()
    key = secrets.token_urlsafe(16)
    with open(_path(key), "wb") as f:
        f.write(data)
    ctype = content_type if content_type and content_type.startswith("image/") else "image/jpeg"
    return apartment_photo_repo.create(db, agency_id, apartment_id, key, ctype, order)


def add_blobs(
    db, agency_id: int, apartment_id: int, blobs: List[Tuple[bytes, str]]
) -> List[dict]:
    """Сохранить набор загруженных файлов (bytes + content_type)."""
    _require_apartment(db, agency_id, apartment_id)
    existing = apartment_photo_repo.count_for(db, agency_id, apartment_id)
    order = apartment_photo_repo.max_sort_order(db, agency_id, apartment_id) + 1

    saved = 0
    for data, ctype in blobs:
        if existing + saved >= MAX_PHOTOS:
            break
        if not data:
            continue
        if len(data) > MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Фото больше {MAX_BYTES // (1024 * 1024)} МБ — слишком большое.",
            )
        if ctype and not ctype.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Можно загружать только изображения.",
            )
        _save_one(db, agency_id, apartment_id, data, ctype or "image/jpeg", order)
        order += 1
        saved += 1

    if saved == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нет фото для загрузки или достигнут лимит.",
        )
    _sync_cover(db, agency_id, apartment_id)
    db.commit()
    return [to_out(p) for p in apartment_photo_repo.list_for(db, agency_id, apartment_id)]


def _fetch(url: str, max_bytes: int) -> Tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
        data = resp.read(max_bytes + 1)
        ctype = resp.headers.get("Content-Type", "") or ""
    if len(data) > max_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл слишком большой.")
    return data, ctype


def _extract_image_urls(page_html: str) -> List[str]:
    """Достать ссылки на фото из HTML поста Telegram (и og:image как запас)."""
    urls: List[str] = []
    # Фото в Telegram-виджете: background-image:url('...').
    for m in re.findall(r"background-image:\s*url\('([^']+)'\)", page_html):
        urls.append(m)
    # Запасной вариант — превью Open Graph.
    for m in re.findall(r'<meta\s+property="og:image"\s+content="([^"]+)"', page_html):
        urls.append(m)
    # Чистим HTML-экранирование и оставляем только картинки, без дублей.
    seen = set()
    result = []
    for u in urls:
        u = html_lib.unescape(u).strip()
        if not u.startswith("http"):
            continue
        if u in seen:
            continue
        seen.add(u)
        result.append(u)
    return result


def import_from_telegram(db, agency_id: int, apartment_id: int, url: str) -> List[dict]:
    """
    Импортировать все фото из поста открытого Telegram-канала по ссылке.
    Поддерживает ссылки вида https://t.me/<канал>/<номер>.
    """
    _require_apartment(db, agency_id, apartment_id)
    url = (url or "").strip()
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пустая ссылка.")

    # Нормализуем ссылку и берём «встраиваемую» версию поста (там видны фото).
    base = url.split("#")[0].split("?")[0]
    if "t.me/" in base or "telegram.me/" in base:
        fetch_url = base + "?embed=1&mode=tme"
    else:
        fetch_url = base

    try:
        page, _ = _fetch(fetch_url, MAX_HTML_BYTES)
        page_html = page.decode("utf-8", errors="ignore")
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось открыть ссылку. Проверьте, что канал открытый.",
        )

    image_urls = _extract_image_urls(page_html)
    if not image_urls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="По ссылке не найдено фотографий. Убедитесь, что в посте есть фото и канал открытый.",
        )

    existing = apartment_photo_repo.count_for(db, agency_id, apartment_id)
    order = apartment_photo_repo.max_sort_order(db, agency_id, apartment_id) + 1
    saved = 0
    for img in image_urls:
        if existing + saved >= MAX_PHOTOS:
            break
        try:
            data, ctype = _fetch(img, MAX_BYTES)
        except Exception:  # noqa: BLE001
            continue
        if not data:
            continue
        if ctype and not ctype.startswith("image/"):
            # Telegram-CDN иногда не указывает тип — пропускаем только если явно не картинка.
            if ctype.startswith("text/") or ctype.startswith("application/"):
                continue
        _save_one(db, agency_id, apartment_id, data, ctype or "image/jpeg", order)
        order += 1
        saved += 1

    if saved == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось загрузить фото по ссылке.",
        )
    _sync_cover(db, agency_id, apartment_id)
    db.commit()
    return [to_out(p) for p in apartment_photo_repo.list_for(db, agency_id, apartment_id)]


def delete_photo(db, agency_id: int, apartment_id: int, photo_id: int) -> None:
    photo = apartment_photo_repo.get(db, agency_id, apartment_id, photo_id)
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Фото не найдено.")
    key = photo.storage_key
    apartment_photo_repo.delete(db, photo)
    db.flush()
    _sync_cover(db, agency_id, apartment_id)
    db.commit()
    # Файл удаляем после коммита (если не вышло — не критично, метаданных уже нет).
    try:
        os.remove(_path(key))
    except OSError:
        pass


def purge_apartment(db, agency_id: int, apartment_id: int) -> None:
    """Удалить все фото объекта (файлы + строки). Вызывается при удалении объекта."""
    keys = apartment_photo_repo.list_keys_for_apartment(db, apartment_id)
    for p in apartment_photo_repo.list_for(db, agency_id, apartment_id):
        apartment_photo_repo.delete(db, p)
    db.flush()
    for key in keys:
        try:
            os.remove(_path(key))
        except OSError:
            pass


def file_for(db, key: str) -> Optional[Tuple[str, str]]:
    """Вернуть (путь_к_файлу, content_type) для отдачи, либо None."""
    photo = apartment_photo_repo.get_by_key(db, key)
    if photo is None:
        return None
    path = _path(key)
    if not os.path.exists(path):
        return None
    return path, photo.content_type
