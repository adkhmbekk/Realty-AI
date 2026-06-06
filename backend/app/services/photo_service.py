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
import asyncio
import html as html_lib
import ipaddress
import logging
import os
import re
import secrets
import socket
import time
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import status
from fastapi.concurrency import run_in_threadpool

from app.config import settings
from app.core.errors import AppError
from app.repositories import apartment_photo_repo, apartment_repo

logger = logging.getLogger("uvicorn.error")

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
        raise AppError("only_http_links", status.HTTP_400_BAD_REQUEST)
    host = parsed.hostname
    if not host:
        raise AppError("invalid_link", status.HTTP_400_BAD_REQUEST)
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:  # noqa: BLE001
        raise AppError("link_host_unresolved", status.HTTP_400_BAD_REQUEST)
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
            raise AppError("link_internal_blocked", status.HTTP_400_BAD_REQUEST)


def _ensure_dir() -> None:
    os.makedirs(settings.photos_dir, exist_ok=True)


def _path(key: str) -> str:
    return os.path.join(settings.photos_dir, key)


# Максимальный размер стороны изображения после сжатия (px).
MAX_DIM = 2048

# Допустимые типы итогового (сохраняемого и отдаваемого) изображения.
_OUTPUT_IMAGE_TYPES = {"image/jpeg", "image/png"}


def _process_image(data: bytes, content_type: str):
    """
    Привести изображение к безопасному виду: открыть растровым декодером
    (Pillow), повернуть по EXIF, уменьшить до MAX_DIM по большей стороне и
    ПЕРЕКОДИРОВАТЬ в JPEG (или PNG при наличии прозрачности).

    Перекодирование — это и оптимизация (меньше вес), и ЗАЩИТА: то, что Pillow
    не может декодировать как растровое изображение (SVG со скриптом, HTML,
    произвольные файлы), сюда не пройдёт — мы поднимаем ошибку «только
    изображения». Тем самым исключаем сохранение активного содержимого (SVG/
    HTML), которое потом могло бы исполниться в браузере (Stored XSS).
    """
    import io

    from PIL import Image, ImageOps

    # Ограничение на число пикселей — защита от «декомпрессионных бомб»
    # (маленький файл, разворачивающийся в гигантское изображение → OOM).
    Image.MAX_IMAGE_PIXELS = 40_000_000

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001
        # Не растровое изображение (SVG/HTML/мусор) — отклоняем.
        raise AppError("only_images", status.HTTP_400_BAD_REQUEST) from exc

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
    img.convert("RGB").save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue(), "image/jpeg"


def public_url(key: str) -> str:
    return f"/api/v1/photos/{key}"


def to_out(photo) -> dict:
    return {"id": photo.id, "url": public_url(photo.storage_key), "sort_order": photo.sort_order}


def _require_apartment(db, agency_id: int, apartment_id: int):
    apt = apartment_repo.get_by_id(db, agency_id, apartment_id)
    if apt is None:
        raise AppError("apartment_not_found", status.HTTP_404_NOT_FOUND)
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
    # Перекодируем перед сохранением (оптимизация + защита: только растровые
    # изображения; SVG/HTML/мусор будут отклонены внутри _process_image).
    data, content_type = _process_image(data, content_type or "image/jpeg")
    key = secrets.token_urlsafe(16)
    with open(_path(key), "wb") as f:
        f.write(data)
    # Тип всегда из белого списка (image/jpeg | image/png) — на всякий случай
    # подстраховываемся явной проверкой.
    ctype = content_type if content_type in _OUTPUT_IMAGE_TYPES else "image/jpeg"
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
            raise AppError(
                "photo_too_large_mb",
                status.HTTP_400_BAD_REQUEST,
                mb=MAX_BYTES // (1024 * 1024),
            )
        # Быстрый отбой по типу: только растровые изображения. SVG (image/svg+xml)
        # и прочий «активный» контент отклоняем явно (он может нести скрипт).
        # Окончательная проверка — перекодирование растровым декодером в _save_one.
        ctype_l = (ctype or "").lower()
        if ctype_l and (
            not ctype_l.startswith("image/") or "svg" in ctype_l or "xml" in ctype_l
        ):
            raise AppError("only_images", status.HTTP_400_BAD_REQUEST)
        _save_one(db, agency_id, apartment_id, data, ctype or "image/jpeg", order)
        order += 1
        saved += 1

    if saved == 0:
        raise AppError("no_photos_or_limit", status.HTTP_400_BAD_REQUEST)
    _sync_cover(db, agency_id, apartment_id)
    db.commit()
    return [to_out(p) for p in apartment_photo_repo.list_for(db, agency_id, apartment_id)]


# Таймаут на сетевые операции импорта (на соединение и на чтение).
_IMPORT_TIMEOUT = httpx.Timeout(8.0, connect=8.0)
# Сколько фото качаем одновременно (ограничение, чтобы не раздувать память/сеть).
_IMPORT_CONCURRENCY = 5


async def _afetch(client: httpx.AsyncClient, url: str, max_bytes: int) -> Tuple[bytes, str]:
    """
    Скачать содержимое по ссылке с защитой от SSRF и без следования редиректам.

    - _assert_public_url (резолв только в публичные адреса) выполняем в пуле
      потоков, т.к. getaddrinfo блокирующий;
    - httpx-клиент создаётся с follow_redirects=False, поэтому Location-редирект
      НЕ выполняется автоматически (иначе проверку адреса можно было бы обойти);
      любой ответ 3xx трактуем как ошибку;
    - читаем потоково и обрываемся при превышении max_bytes (защита памяти).
    """
    await run_in_threadpool(_assert_public_url, url)
    async with client.stream(
        "GET", url, headers={"User-Agent": _UA, "Accept": "*/*"}
    ) as resp:
        if 300 <= resp.status_code < 400:
            raise AppError("link_open_failed", status.HTTP_400_BAD_REQUEST)
        ctype = resp.headers.get("Content-Type", "") or ""
        chunks: List[bytes] = []
        total = 0
        async for chunk in resp.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise AppError("file_too_large", status.HTTP_400_BAD_REQUEST)
            chunks.append(chunk)
    return b"".join(chunks), ctype


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


def _save_downloaded(
    db, agency_id: int, apartment_id: int, items: List[Tuple[bytes, str]], slots: int
) -> int:
    """
    Сохранить уже скачанные изображения (синхронно, в одном потоке — Session не
    потокобезопасна). Возвращает число фактически сохранённых.
    """
    order = apartment_photo_repo.max_sort_order(db, agency_id, apartment_id) + 1
    saved = 0
    for data, ctype in items:
        if saved >= slots:
            break
        if not data:
            continue
        ctype_l = (ctype or "").lower()
        if ctype_l and (not ctype_l.startswith("image/") or "svg" in ctype_l or "xml" in ctype_l):
            # Явно не растровое изображение (HTML/SVG/прочее) — пропускаем.
            continue
        try:
            _save_one(db, agency_id, apartment_id, data, ctype or "image/jpeg", order)
        except Exception:  # noqa: BLE001
            # Не удалось декодировать как изображение — пропускаем, чтобы один
            # плохой файл не срывал импорт остальных.
            continue
        order += 1
        saved += 1
    if saved:
        _sync_cover(db, agency_id, apartment_id)
        db.commit()
    return saved


async def import_from_telegram(db, agency_id: int, apartment_id: int, url: str) -> List[dict]:
    """
    Импортировать все фото из поста открытого Telegram-канала по ссылке.
    Поддерживает ссылки вида https://t.me/<канал>/<номер>.

    Фотографии скачиваются ПАРАЛЛЕЛЬНО (быстрее и не «висит»), а сохранение в БД
    идёт в одном потоке. Защита от SSRF и запрет редиректов сохранены.
    """
    await run_in_threadpool(_require_apartment, db, agency_id, apartment_id)
    url = (url or "").strip()
    if not url:
        raise AppError("empty_link", status.HTTP_400_BAD_REQUEST)

    # Нормализуем ссылку и берём «встраиваемую» версию поста (там видны фото).
    base = url.split("#")[0].split("?")[0]
    if not _is_telegram_url(base):
        raise AppError("import_only_telegram", status.HTTP_400_BAD_REQUEST)
    fetch_url = base + "?embed=1&mode=tme"

    existing = await run_in_threadpool(
        apartment_photo_repo.count_for, db, agency_id, apartment_id
    )
    slots = MAX_PHOTOS - existing
    if slots <= 0:
        raise AppError("no_photos_or_limit", status.HTTP_400_BAD_REQUEST)

    async with httpx.AsyncClient(
        follow_redirects=False, timeout=_IMPORT_TIMEOUT
    ) as client:
        try:
            page, _ = await _afetch(client, fetch_url, MAX_HTML_BYTES)
            page_html = page.decode("utf-8", errors="ignore")
        except AppError:
            raise
        except Exception:  # noqa: BLE001
            raise AppError("link_open_failed", status.HTTP_400_BAD_REQUEST)

        image_urls = _extract_image_urls(page_html)
        if not image_urls:
            raise AppError("no_photos_in_post", status.HTTP_400_BAD_REQUEST)

        # Качаем кандидатов параллельно (с ограничением одновременности).
        candidates = image_urls[:MAX_PHOTOS]
        sem = asyncio.Semaphore(_IMPORT_CONCURRENCY)

        async def _download(u: str) -> Optional[Tuple[bytes, str]]:
            async with sem:
                try:
                    data, ctype = await _afetch(client, u, MAX_BYTES)
                except Exception:  # noqa: BLE001
                    return None
                return (data, ctype) if data else None

        # gather сохраняет порядок кандидатов → порядок фото в карточке стабилен.
        results = await asyncio.gather(*[_download(u) for u in candidates])

    downloaded = [r for r in results if r is not None]
    if not downloaded:
        raise AppError("photo_download_failed", status.HTTP_400_BAD_REQUEST)

    saved = await run_in_threadpool(
        _save_downloaded, db, agency_id, apartment_id, downloaded, slots
    )
    if saved == 0:
        raise AppError("photo_download_failed", status.HTTP_400_BAD_REQUEST)

    return await run_in_threadpool(
        lambda: [to_out(p) for p in apartment_photo_repo.list_for(db, agency_id, apartment_id)]
    )


def delete_photo(db, agency_id: int, apartment_id: int, photo_id: int) -> None:
    photo = apartment_photo_repo.get(db, agency_id, apartment_id, photo_id)
    if photo is None:
        raise AppError("photo_not_found", status.HTTP_404_NOT_FOUND)
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


def purge_agency(db, agency_id: int) -> None:
    """
    Удалить ВСЕ фото агентства (файлы с диска + строки в БД). Вызывается при
    удалении агентства, чтобы не оставлять «осиротевшие» файлы на диске и не
    держать объекты ссылками (что раньше ломало удаление агентства с фото).
    """
    keys = apartment_photo_repo.list_keys_for_agency(db, agency_id)
    apartment_photo_repo.delete_for_agency(db, agency_id)
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


def sweep_orphan_photos(db, grace_hours: int = 24) -> int:
    """
    Удалить «осиротевшие» файлы фото: те, что лежат в photos_dir, но не имеют
    строки в БД (storage_key), И старше grace_hours.

    Такие файлы могут появиться, если процесс прервался между записью файла на
    диск и фиксацией строки в БД (порядок создания: файл → строка → commit, см.
    M4). У РЕАЛЬНОГО фото строка в БД всегда есть после commit, а commit
    происходит в рамках того же запроса — поэтому при grace_hours=24 файл с
    «незавершённой» загрузкой не может оказаться свежее суток. Ложных удалений
    нет. Возвращает число удалённых файлов.
    """
    d = settings.photos_dir
    if not os.path.isdir(d):
        return 0
    known = set(apartment_photo_repo.all_storage_keys(db))
    cutoff = time.time() - grace_hours * 3600
    removed = 0
    for name in os.listdir(d):
        if name in known:
            continue  # есть строка в БД — это настоящее фото, не трогаем
        path = os.path.join(d, name)
        try:
            if not os.path.isfile(path):
                continue
            if os.path.getmtime(path) > cutoff:
                continue  # слишком свежий — мог быть в процессе загрузки
            os.remove(path)
            removed += 1
            logger.info("Подчистка: удалён осиротевший файл фото %s", name)
        except Exception:  # noqa: BLE001
            pass
    return removed
