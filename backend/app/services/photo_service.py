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
import ipaddress
import os
import re
import secrets
import socket
import urllib.request
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from fastapi import HTTPException, status

from app.config import settings
from app.repositories import apartment_photo_repo, apartment_repo

MAX_PHOTOS = 20
MAX_BYTES = 12 * 1024 * 1024  # 12 МБ на файл
MAX_HTML_BYTES = 4 * 1024 * 1024
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# Импорт фотографий разрешён только из Telegram.
_ALLOWED_IMPORT_HOSTS = ("t.me", "telegram.me")


def _is_telegram_url(url: str) -> bool:
    """True, если ссылка ведёт на Telegram (t.me / telegram.me)."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return False
    return any(host == h or host.endswith("." + h) for h in _ALLOWED_IMPORT_HOSTS)


def _assert_public_url(url: str) -> None:
    """
    Защита от SSRF (подмены адреса). Разрешаем загрузку только по http/https и
    только с публичных адресов. Блокируем обращения во внутреннюю сеть
    (localhost, 10.x, 192.168.x, 169.254.x и т.п.), чтобы по присланной ссылке
    нельзя было «достучаться» до внутренних сервисов сервера.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поддерживаются только ссылки http/https.",
        )
    host = parsed.hostname
    if not host:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректная ссылка.",
        )
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось определить адрес ссылки.",
        )
    for info in infos:
        ip_str = info[4][0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ссылка ведёт во внутреннюю сеть и заблокирована.",
            )


def _ensure_dir() -> None:
    os.makedirs(settings.photos_dir, exist_ok=True)


def _path(key: str) -> str:
    return os.path.join(settings.photos_dir, key)


# Максимальный размер стороны изображения после сжатия (px).
MAX_DIM = 1920


def _process_image(data: bytes, content_type: str):
    """
    Сжать изображение: повернуть по EXIF, уменьшить до MAX_DIM по большей стороне,
    перекодировать в JPEG (или PNG при наличии прозрачности). Это резко уменьшает
    вес фото — важно для быстрой загрузки и отдачи через туннель/мобильный интернет.
    При любой ошибке возвращаем исходные байты без изменений.
    """
    try:
        import io

        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(data))
        img.load()
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:  # noqa: BLE001
            pass
        if max(img.size) > MAX_DIM:
            img.thumbnail((MAX_DIM, MAX_DIM))
        has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        out = io.BytesIO()
        if has_alpha:
            img.convert("RGBA").save(out, format="PNG", optimize=True)
            return out.getvalue(), "image/png"
        img.convert("RGB").save(out, format="JPEG", quality=88, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001
        return data, content_type


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
    # Сжимаем перед сохранением (уменьшение размера + перекодирование).
    data, content_type = _process_image(data, content_type or "image/jpeg")
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
    _assert_public_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
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
    if not _is_telegram_url(base):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Импорт работает только со ссылками Telegram (t.me/<канал>/<номер>).",
        )
    fetch_url = base + "?embed=1&mode=tme"

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


def read_blobs_for_share(
    db, agency_id: int, apartment_id: int, limit: int = 10
) -> List[Tuple[bytes, str]]:
    """
    Прочитать с диска байты фотографий объекта (до limit штук) для отправки
    альбомом через бота. Возвращает список (байты, content_type).
    """
    blobs: List[Tuple[bytes, str]] = []
    for photo in apartment_photo_repo.list_for(db, agency_id, apartment_id):
        if len(blobs) >= limit:
            break
        path = _path(photo.storage_key)
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            continue
        if data:
            blobs.append((data, photo.content_type or "image/jpeg"))
    return blobs



def decode_data_url(s: str) -> Tuple[bytes, str]:
    """
    Декодировать изображение из строки base64 / data-URL.
    Возвращает (байты, content_type). При ошибке — (b"", "image/jpeg").
    """
    import base64

    if not s:
        return b"", "image/jpeg"
    ctype = "image/jpeg"
    payload = s
    if s.startswith("data:"):
        header, _, b64 = s.partition(",")
        payload = b64
        if ":" in header and ";" in header:
            ctype = header[header.index(":") + 1 : header.index(";")] or "image/jpeg"
    try:
        data = base64.b64decode(payload, validate=False)
    except Exception:  # noqa: BLE001
        data = b""
    return data, ctype
