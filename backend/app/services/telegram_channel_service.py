"""
Массовый импорт объектов из открытого Telegram-канала — Этап 3.1.

Идея: у открытого канала есть веб-лента https://t.me/s/<канал> (та же, что видна
без входа в Telegram). Мы читаем её постранично, разбираем каждый пост (текст +
фото), отдаём текст в Gemini (как при импорте одного объявления) и создаём
объекты в базе. Фото поста прикрепляются к объекту.

Постранично — по курсору `before` (id самого старого поста на странице): один
запрос обрабатывает одну страницу (~16–20 постов), а фронтенд крутит цикл и
показывает прогресс. Так мы не упираемся в таймауты на больших каналах, а
«весь канал» прокачивается за несколько проходов (от новых к старым).

Защита от дублей: пост, уже импортированный ранее (совпал source_link), пропускаем
— поэтому повторный проход не плодит копии.
"""
import html as html_lib
import logging
import re
from typing import List, Optional

import httpx
from fastapi import status as http_status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models.apartment import Apartment
from app.schemas.apartment import ApartmentCreate
from app.services import (
    apartment_service,
    dictionary_service,
    listing_import_service,
    photo_service,
)

logger = logging.getLogger("uvicorn.error")

_FEED_URL = "https://t.me/s/{channel}"
_UA = photo_service._UA
_FETCH_TIMEOUT = httpx.Timeout(15.0, connect=8.0)
# Сколько постов разбираем ИИ за ОДИН запрос (одну страницу). Бесплатный Gemini
# жёстко лимитирует частоту, поэтому шлём ПОСЛЕДОВАТЕЛЬНО и небольшими порциями —
# так каждый HTTP-запрос остаётся коротким, а фронтенд идёт страницами с паузами.
_MAX_AI_PER_PAGE = 6
_MAX_PHOTOS_PER_OBJ = 10     # столько фото на объект при массовом импорте
# Структурные поля: если ни одного нет — это, скорее всего, не объявление
# (приветствие, реклама и т.п.), такой пост пропускаем.
_STRUCTURAL = ("type", "price", "rooms", "area", "land_area", "district", "address", "owner_phone")


def normalize_channel(raw: str) -> str:
    """Из ввода пользователя получить username канала. Бросает ошибку, если не похоже."""
    s = (raw or "").strip()
    if not s:
        raise AppError("tg_channel_invalid", http_status.HTTP_400_BAD_REQUEST)
    s = s.replace("https://", "").replace("http://", "")
    # t.me/s/name, t.me/name, telegram.me/name → берём сегмент после домена.
    m = re.search(r"(?:t\.me|telegram\.me)/(?:s/)?([^/?#]+)", s)
    if m:
        s = m.group(1)
    s = s.lstrip("@").strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_]{3,32}", s):
        raise AppError("tg_channel_invalid", http_status.HTTP_400_BAD_REQUEST)
    return s


def _strip_tags(html: str) -> str:
    """Текст поста: <br> → перевод строки, убрать теги, снять экранирование."""
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", html)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def parse_feed(html: str) -> List[dict]:
    """Разобрать HTML ленты канала → список постов [{id, text, images}]."""
    posts: List[dict] = []
    # Делим страницу на блоки сообщений по обёртке tgme_widget_message_wrap.
    starts = [m.start() for m in re.finditer(r'<div class="tgme_widget_message_wrap', html)]
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(html)
        chunk = html[start:end]

        mid = re.search(r'data-post="[^"/]+/(\d+)"', chunk)
        if not mid:
            continue
        post_id = int(mid.group(1))

        # Текст поста (может отсутствовать — пост из одних фото).
        text_parts = re.findall(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            chunk, flags=re.DOTALL,
        )
        text = _strip_tags(" ".join(text_parts)) if text_parts else ""

        # Фото поста: background-image:url('...').
        images: List[str] = []
        seen = set()
        for u in re.findall(r"background-image:\s*url\('([^']+)'\)", chunk):
            u = html_lib.unescape(u).strip()
            if u.startswith("http") and u not in seen:
                seen.add(u)
                images.append(u)

        posts.append({"id": post_id, "text": text, "images": images})
    return posts


def _fetch_feed(channel: str, before: Optional[int]) -> str:
    params = {"before": before} if before else None
    try:
        with httpx.Client(follow_redirects=True, timeout=_FETCH_TIMEOUT) as client:
            r = client.get(
                _FEED_URL.format(channel=channel),
                params=params,
                headers={"User-Agent": _UA, "Accept-Language": "ru,en;q=0.8"},
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("TG-импорт: не удалось открыть ленту %s: %s", channel, exc)
        raise AppError("tg_channel_unreachable", http_status.HTTP_400_BAD_REQUEST) from exc
    if r.status_code >= 400:
        raise AppError("tg_channel_unreachable", http_status.HTTP_400_BAD_REQUEST)
    return r.text


async def scan_page(
    db: Session, agency_id: int, created_by: Optional[int],
    channel_raw: str, before: Optional[int],
) -> dict:
    """
    Обработать порцию ленты канала: разобрать посты, извлечь поля ИИ (строго
    ПОСЛЕДОВАТЕЛЬНО, не более _MAX_AI_PER_PAGE за запрос), создать объекты +
    прикрепить фото. Вернуть статистику и курсор next_before для продолжения.

    Курсор продвигается только по «финализированным» постам (созданным, явно
    пропущенным или с ошибкой ИИ). Если упёрлись в лимит частоты Gemini (429),
    помечаем rate_limited и НЕ двигаем курсор за необработанный пост — фронтенд
    сделает паузу и повторит этот же пост позже.
    """
    channel = normalize_channel(channel_raw)
    html = await run_in_threadpool(_fetch_feed, channel, before)
    posts = parse_feed(html)
    if not posts:
        return {"channel": channel, "created": 0, "skipped": 0, "failed": 0,
                "next_before": before, "rate_limited": False, "done": True}

    districts = [
        d.value for d in dictionary_service.list_dictionaries(db, agency_id, category="district")
    ]

    # Защита от дублей: какие посты этого канала уже импортированы.
    urls = {p["id"]: f"https://t.me/{channel}/{p['id']}" for p in posts}
    existing = {
        row[0] for row in db.query(Apartment.source_link)
        .filter(Apartment.agency_id == agency_id, Apartment.source_link.in_(list(urls.values())))
        .all()
    }

    created = skipped = failed = ai_done = 0
    rate_limited = False
    advanced_to: Optional[int] = None  # самый старый пост, который мы «закрыли»

    # От новых к старым.
    for p in sorted(posts, key=lambda x: x["id"], reverse=True):
        # Дубль или пост без текста — закрываем сразу (двигаем курсор).
        if urls[p["id"]] in existing or not p["text"]:
            skipped += 1
            advanced_to = p["id"]
            continue
        # Лимит на запрос исчерпан — остальное оставим следующему проходу.
        if ai_done >= _MAX_AI_PER_PAGE:
            break
        try:
            fields = await run_in_threadpool(
                listing_import_service.extract_fields_from_text, p["text"], districts
            )
        except AppError as exc:
            if exc.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS:
                # Лимит частоты: НЕ закрываем пост (повторим позже), тормозим.
                rate_limited = True
                break
            failed += 1
            ai_done += 1
            advanced_to = p["id"]
            continue
        except Exception as exc:  # noqa: BLE001
            logger.info("TG-импорт: ИИ-разбор поста %s: %s", p["id"], exc)
            failed += 1
            ai_done += 1
            advanced_to = p["id"]
            continue

        ai_done += 1
        if not fields or not any(fields.get(k) is not None for k in _STRUCTURAL):
            skipped += 1
            advanced_to = p["id"]
            continue
        body = {k: v for k, v in fields.items() if v is not None and k != "warnings"}
        body.pop("photo_urls", None)
        body["source_link"] = urls[p["id"]]
        try:
            apt = await run_in_threadpool(
                apartment_service.create_apartment,
                db, agency_id, created_by, ApartmentCreate(**body),
            )
        except AppError:
            skipped += 1
            advanced_to = p["id"]
            continue
        created += 1
        advanced_to = p["id"]
        if p["images"]:
            try:
                await photo_service.import_from_image_urls(
                    db, agency_id, apt.id, p["images"][:_MAX_PHOTOS_PER_OBJ]
                )
            except Exception as exc:  # noqa: BLE001
                logger.info("TG-импорт: фото поста %s не прикреплены: %s", p["id"], exc)

    next_before = advanced_to if advanced_to is not None else before
    return {
        "channel": channel,
        "created": created,
        "skipped": skipped,
        "failed": failed,
        "next_before": next_before,
        "rate_limited": rate_limited,
        "done": False,
    }
