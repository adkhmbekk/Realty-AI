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
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import status as http_status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.subscription import agency_is_active
from app.db.models.apartment import Apartment
from app.db.models.watched_channel import WatchedChannel
from app.repositories import agency_repo
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

# Признаки, что объект уже ПРОДАН / снят / неактуален (где угодно в тексте —
# в начале или в конце). Такие посты не добавляем; если это reply на пост —
# исходный объект архивируем. ВАЖНО: НЕ ловим «продажа/продаётся/продаю»
# (это активные объявления) — только завершённое «продано/продан/sotildi».
_INACTIVE_RE = re.compile(
    r"прода(?:но|на|ны|н)\b"
    r"|sotildi|sotilgan|sotib\s+yubor"
    r"|\bsold\b"
    r"|неактуал|не\s*актуал"
    r"|снят[оа]?\s+с\s+продаж",
    re.IGNORECASE,
)


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
    """Разобрать HTML ленты канала → список постов [{id, text, images, reply_to}]."""
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

        # Это ответ (reply) на другой пост канала? Вытаскиваем id родителя и
        # УБИРАЕМ блок-цитату из чанка, чтобы не принять текст исходного поста
        # за текст ответа (из-за этого раньше плодились дубли).
        reply_to: Optional[int] = None
        rep = re.search(
            r'<a class="tgme_widget_message_reply"[^>]*href="[^"]*?/(\d+)"[^>]*>.*?</a>',
            chunk, flags=re.DOTALL,
        )
        if rep:
            reply_to = int(rep.group(1))
            chunk = chunk[: rep.start()] + chunk[rep.end():]

        # Текст поста (может отсутствовать — пост из одних фото).
        text_parts = re.findall(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            chunk, flags=re.DOTALL,
        )
        text = _strip_tags(" ".join(text_parts)) if text_parts else ""

        # Фото поста: background-image:url('...'). Видео в ленту попадают как
        # отдельные плееры без background-image — поэтому берём только фото.
        images: List[str] = []
        seen = set()
        for u in re.findall(r"background-image:\s*url\('([^']+)'\)", chunk):
            u = html_lib.unescape(u).strip()
            if u.startswith("http") and u not in seen:
                seen.add(u)
                images.append(u)

        posts.append({"id": post_id, "text": text, "images": images, "reply_to": reply_to})
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
                "archived": 0, "next_before": before, "rate_limited": False, "done": True}

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

    created = skipped = failed = archived = ai_done = 0
    rate_limited = False
    advanced_to: Optional[int] = None  # самый старый пост, который мы «закрыли»

    # Пре-проход по ОТВЕТАМ (reply): если под постом ответ «продано/неактуально»,
    # помечаем исходный пост как проданный. Уже импортированный объект-родитель
    # сразу архивируем; ещё не импортированный — просто не возьмём ниже.
    sold_parents = {
        p["reply_to"]
        for p in posts
        if p["reply_to"] and p["text"] and _INACTIVE_RE.search(p["text"])
    }
    if sold_parents:
        parent_links = [f"https://t.me/{channel}/{pid}" for pid in sold_parents]
        rows = (
            db.query(Apartment.id, Apartment.source_link)
            .filter(Apartment.agency_id == agency_id,
                    Apartment.source_link.in_(parent_links),
                    Apartment.deleted_at.is_(None))
            .all()
        )
        for aid, _link in rows:
            try:
                await run_in_threadpool(apartment_service.delete_apartment, db, agency_id, aid)
                archived += 1
            except Exception as exc:  # noqa: BLE001
                logger.info("TG-импорт: не удалось архивировать проданный %s: %s", aid, exc)

    # От новых к старым.
    for p in sorted(posts, key=lambda x: x["id"], reverse=True):
        # Сообщения-ОТВЕТЫ — это статус/комментарий, а не объявление: пропускаем.
        if p["reply_to"]:
            skipped += 1
            advanced_to = p["id"]
            continue
        # Дубль, пост без текста, помеченный проданным (через reply или прямо в
        # тексте — в начале или в конце) — закрываем сразу (двигаем курсор).
        if (urls[p["id"]] in existing or not p["text"]
                or p["id"] in sold_parents or _INACTIVE_RE.search(p["text"])):
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
        body["source"] = f"@{channel}"
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
        "archived": archived,
        "next_before": next_before,
        "rate_limited": rate_limited,
        "done": False,
    }


# ── Фоновый авто-импорт: слежение за каналами ───────────────────────────────
# Сервер сам периодически проверяет «слушаемые» каналы и добавляет НОВЫЕ посты
# (id > last_post_id). Это и фоновый импорт (не нужен открытый экран), и решение
# «новый пост → сразу в базе».
_AUTO_MAX_NEW = 12  # сколько ИИ-разборов делаем за один тик одного канала
# Максимум страниц ленты за один проход слежки (защита от бесконечной прокрутки).
# 25 страниц с запасом покрывают любую реальную пачку новых постов за тик; если
# канал выложил ещё больше — остаток доберётся на следующих тиках.
_MAX_FEED_PAGES = 25


async def _collect_new_posts(channel: str, last_id: int) -> List[dict]:
    """Собрать ВСЕ посты канала новее last_id, ЛИСТАЯ ленту назад (параметр
    before), пока не дойдём до курсора.

    Зачем: t.me/s по умолчанию отдаёт только последнюю страницу. Если за тик в
    канал вышла пачка постов (например 32), на странице помещаются лишь самые
    свежие — старые из пачки терялись, а курсор перепрыгивал через них. Теперь
    собираем всё новее курсора и импортируем по порядку (старые → новые)."""
    collected: dict = {}
    before: Optional[int] = None
    for _ in range(_MAX_FEED_PAGES):
        html = await run_in_threadpool(_fetch_feed, channel, before)
        page = parse_feed(html)
        if not page:
            break
        for p in page:
            if p["id"] > last_id:
                collected[p["id"]] = p
        page_min = min(p["id"] for p in page)
        if page_min <= last_id:
            break  # дошли до уже учтённых — старее новых постов нет
        before = page_min
    return list(collected.values())


def _newest_post_id(channel: str) -> int:
    """id самого свежего поста канала (0 — если постов нет). Может бросить AppError."""
    html = _fetch_feed(channel, None)
    posts = parse_feed(html)
    return max((p["id"] for p in posts), default=0)


def add_watch(db: Session, agency_id: int, created_by: Optional[int], channel_raw: str) -> WatchedChannel:
    """Включить слежение за каналом. Курсор ставим на текущий свежий пост —
    история не импортируется (для неё есть ручной импорт), берём только новое."""
    channel = normalize_channel(channel_raw)
    newest = _newest_post_id(channel)  # заодно проверяет, что канал доступен
    existing = (
        db.query(WatchedChannel)
        .filter(WatchedChannel.agency_id == agency_id, WatchedChannel.channel == channel)
        .first()
    )
    if existing is not None:
        existing.enabled = True
        existing.created_by = created_by
        existing.last_post_id = max(existing.last_post_id or 0, newest)
        db.commit()
        db.refresh(existing)
        return existing
    w = WatchedChannel(
        agency_id=agency_id, channel=channel, last_post_id=newest,
        created_by=created_by, enabled=True,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


def list_watches(db: Session, agency_id: int) -> List[WatchedChannel]:
    return (
        db.query(WatchedChannel)
        .filter(WatchedChannel.agency_id == agency_id)
        .order_by(WatchedChannel.created_at.desc())
        .all()
    )


def remove_watch(db: Session, agency_id: int, watch_id: int) -> None:
    w = (
        db.query(WatchedChannel)
        .filter(WatchedChannel.agency_id == agency_id, WatchedChannel.id == watch_id)
        .first()
    )
    if w is not None:
        db.delete(w)
        db.commit()


async def auto_import_channel(db: Session, watch: WatchedChannel, max_new: int = _AUTO_MAX_NEW) -> int:
    """
    Один тик слежения за каналом: добрать НОВЫЕ посты (id > last_post_id) от
    старых к новым (не больше max_new ИИ-разборов), создать объекты, продвинуть
    курсор. Reply «продано» архивирует исходный объект; проданные/неактуальные и
    дубли (тот же пост) пропускаются, но курсор через них продвигается.
    """
    channel = watch.channel
    last_id = watch.last_post_id or 0
    # Собираем ВСЕ новые посты (листая ленту назад до курсора), а не только
    # последнюю страницу — иначе при большой пачке старые посты терялись.
    posts = await _collect_new_posts(channel, last_id)
    watch.last_checked_at = datetime.now(timezone.utc)
    if not posts:
        db.commit()
        return 0

    # Архивируем объекты, под постами которых появился ответ «продано».
    sold_parents = {
        p["reply_to"] for p in posts
        if p["reply_to"] and p["text"] and _INACTIVE_RE.search(p["text"])
    }
    if sold_parents:
        parent_links = [f"https://t.me/{channel}/{pid}" for pid in sold_parents]
        rows = (
            db.query(Apartment.id)
            .filter(Apartment.agency_id == watch.agency_id,
                    Apartment.source_link.in_(parent_links),
                    Apartment.deleted_at.is_(None))
            .all()
        )
        for (aid,) in rows:
            try:
                await run_in_threadpool(apartment_service.delete_apartment, db, watch.agency_id, aid)
            except Exception as exc:  # noqa: BLE001
                logger.info("Авто-импорт: не удалось архивировать %s: %s", aid, exc)

    last_id = watch.last_post_id or 0
    new_posts = sorted((p for p in posts if p["id"] > last_id), key=lambda x: x["id"])
    if not new_posts:
        db.commit()
        return 0

    districts = [
        d.value for d in dictionary_service.list_dictionaries(db, watch.agency_id, category="district")
    ]
    urls = {p["id"]: f"https://t.me/{channel}/{p['id']}" for p in new_posts}
    existing = {
        row[0] for row in db.query(Apartment.source_link)
        .filter(Apartment.agency_id == watch.agency_id,
                Apartment.source_link.in_(list(urls.values()))).all()
    }

    created = ai_done = 0
    cursor = last_id
    for p in new_posts:
        pid = p["id"]
        # Ответы, дубли, проданные/неактуальные, пустые — мимо (курсор двигаем).
        if (p["reply_to"] or urls[pid] in existing or not p["text"]
                or pid in sold_parents or _INACTIVE_RE.search(p["text"])):
            cursor = max(cursor, pid)
            continue
        if ai_done >= max_new:
            break  # остаток добежит на следующем тике (id > cursor)
        try:
            fields = await run_in_threadpool(
                listing_import_service.extract_fields_from_text, p["text"], districts
            )
        except AppError as exc:
            if exc.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS:
                break  # лимит — этот пост повторим на следующем тике (курсор не двигаем)
            ai_done += 1
            cursor = max(cursor, pid)
            continue
        except Exception as exc:  # noqa: BLE001
            logger.info("Авто-импорт: ИИ-разбор поста %s: %s", pid, exc)
            ai_done += 1
            cursor = max(cursor, pid)
            continue
        ai_done += 1
        if not fields or not any(fields.get(k) is not None for k in _STRUCTURAL):
            cursor = max(cursor, pid)
            continue
        body = {k: v for k, v in fields.items() if v is not None and k != "warnings"}
        body.pop("photo_urls", None)
        body["source_link"] = urls[pid]
        body["source"] = f"@{channel}"
        try:
            apt = await run_in_threadpool(
                apartment_service.create_apartment,
                db, watch.agency_id, watch.created_by, ApartmentCreate(**body),
            )
        except AppError:
            cursor = max(cursor, pid)
            continue
        created += 1
        cursor = max(cursor, pid)
        if p["images"]:
            try:
                await photo_service.import_from_image_urls(
                    db, watch.agency_id, apt.id, p["images"][:_MAX_PHOTOS_PER_OBJ]
                )
            except Exception as exc:  # noqa: BLE001
                logger.info("Авто-импорт: фото поста %s не прикреплены: %s", pid, exc)

    watch.last_post_id = max(watch.last_post_id or 0, cursor)
    db.commit()
    return created


async def auto_import_all(db: Session, max_channels: int = 100, max_new: int = _AUTO_MAX_NEW) -> int:
    """Тик авто-импорта по всем включённым каналам. Возвращает число созданных объектов."""
    watches = (
        db.query(WatchedChannel)
        .filter(WatchedChannel.enabled.is_(True))
        .limit(max_channels)
        .all()
    )
    total = 0
    for w in watches:
        agency = agency_repo.get_by_id(db, w.agency_id)
        if agency is None:
            continue
        # Клиентские агентства с неактивной подпиской пропускаем; личные — всегда.
        if agency.owner_telegram_id is None and not agency_is_active(agency):
            continue
        try:
            total += await auto_import_channel(db, w, max_new=max_new)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Авто-импорт канала %s (агентство %s): %s", w.channel, w.agency_id, exc)
            db.rollback()
    return total
