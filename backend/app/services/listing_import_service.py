"""
Импорт объявления по ссылке (AI-разбор).

Сценарий:
  1) Пользователь вставляет ссылку на объявление (Telegram, OLX, Joymee и любые
     другие площадки).
  2) Мы загружаем страницу и достаём из неё: мета-теги (Open Graph), разметку
     Schema.org (JSON-LD), видимый текст и ссылки на фотографии.
  3) Текст отправляем в OpenAI (gpt-4o-mini), который извлекает поля объекта в
     строго структурированный JSON (тип, район, цена, комнаты и т.д.). Всё, что
     не подходит под конкретные поля, складывается в «Описание».
  4) Возвращаем поля + ссылки на фото. НИЧЕГО не сохраняем — пользователь видит
     заполненную форму, правит её и только потом сохраняет (фото прикрепляются
     при сохранении через отдельный эндпоинт).

Защита: проверка ссылки (SSRF), ограничение размера страницы, таймауты, понятные
ошибки. Частичные данные — норма (недостающее остаётся null).
"""
import html as html_lib
import json
import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import status

from app.config import settings
from app.core.errors import AppError
from app.services import photo_service

logger = logging.getLogger("uvicorn.error")

# Фиксированные справочники значений (зеркало фронтенда — frontend/src/i18n.ts).
OBJ_TYPE_VALUES = ["Квартира", "Дом", "Коммерция", "Земля", "Участок"]
OBJ_COND_VALUES = [
    "Без ремонта", "Черновая", "White box",
    "Средний ремонт", "Новый ремонт", "Дизайнерский ремонт",
]
FA_VALUES = ["furniture_and_appliances", "furniture_only", "appliances_only", "none"]
CURRENCIES = ["USD", "UZS", "EUR"]
LAND_TYPES = ("Земля", "Участок")

# Ограничения, чтобы не раздувать память/токены.
_MAX_HTML_BYTES = 3 * 1024 * 1024     # не качаем гигантские страницы
_MAX_AI_CHARS = 14_000               # сколько текста отдаём модели
_MAX_IMAGES = 20                     # сколько ссылок на фото возвращаем
_FETCH_TIMEOUT = httpx.Timeout(12.0, connect=8.0)


# ── Загрузка страницы ────────────────────────────────────────────────
def _fetch_html(url: str) -> Tuple[str, str]:
    """
    Скачать HTML страницы. Возвращает (html, final_url).
    Защита от SSRF: исходный адрес обязан резолвиться в публичный IP.
    """
    photo_service._assert_public_url(url)  # бросит AppError при внутреннем адресе
    try:
        with httpx.Client(follow_redirects=True, timeout=_FETCH_TIMEOUT) as client:
            with client.stream(
                "GET", url,
                headers={
                    "User-Agent": photo_service._UA,
                    "Accept": "text/html,application/xhtml+xml,*/*",
                    "Accept-Language": "ru,en;q=0.8",
                },
            ) as resp:
                if resp.status_code >= 400:
                    raise AppError("import_fetch_failed", status.HTTP_400_BAD_REQUEST)
                chunks: List[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > _MAX_HTML_BYTES:
                        break
                    chunks.append(chunk)
                final_url = str(resp.url)
        return b"".join(chunks).decode("utf-8", errors="ignore"), final_url
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.info("Импорт: не удалось загрузить %s: %s", url, exc)
        raise AppError("import_fetch_failed", status.HTTP_400_BAD_REQUEST) from exc


# ── Разбор HTML ──────────────────────────────────────────────────────
def _meta_content(html: str, key: str) -> Optional[str]:
    """Достать содержимое <meta property/name="key" content="...">."""
    for attr in ("property", "name"):
        m = re.search(
            rf'<meta[^>]+{attr}=["\']{re.escape(key)}["\'][^>]*content=["\']([^"\']*)["\']',
            html, re.IGNORECASE,
        )
        if not m:
            m = re.search(
                rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]*{attr}=["\']{re.escape(key)}["\']',
                html, re.IGNORECASE,
            )
        if m:
            return html_lib.unescape(m.group(1)).strip()
    return None


def _all_meta(html: str, key: str) -> List[str]:
    """Все значения <meta property="key" content="..."> (например, несколько og:image)."""
    out = []
    for m in re.finditer(
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]*content=["\']([^"\']*)["\']',
        html, re.IGNORECASE,
    ):
        out.append(html_lib.unescape(m.group(1)).strip())
    return out


def _jsonld_blocks(html: str) -> List[str]:
    """Сырые JSON-LD блоки (Schema.org) — там часто лежат цена, адрес, фото."""
    blocks = []
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.IGNORECASE | re.DOTALL,
    ):
        blocks.append(m.group(1).strip())
    return blocks


def _visible_text(html: str) -> str:
    """Видимый текст страницы: вырезаем скрипты/стили, снимаем теги."""
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", html)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _is_image_url(u: str) -> bool:
    path = urlparse(u).path.lower()
    return path.endswith((".jpg", ".jpeg", ".png", ".webp"))


def _extract_images_generic(html: str, base_url: str) -> List[str]:
    """Ссылки на фото с обычной страницы: og:image, twitter:image, JSON-LD, <img>."""
    found: List[str] = []
    found += _all_meta(html, "og:image")
    found += _all_meta(html, "og:image:secure_url")
    found += _all_meta(html, "twitter:image")
    # Картинки из JSON-LD.
    for block in _jsonld_blocks(html):
        for m in re.finditer(r'"(?:image|contentUrl|thumbnailUrl)"\s*:\s*"([^"]+)"', block):
            found.append(html_lib.unescape(m.group(1)))
        for m in re.finditer(r'"url"\s*:\s*"([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', block, re.IGNORECASE):
            found.append(html_lib.unescape(m.group(1)))
    # <img src> и srcset.
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE):
        found.append(html_lib.unescape(m.group(1)))
    for m in re.finditer(r'srcset=["\']([^"\']+)["\']', html, re.IGNORECASE):
        # берём первый URL из srcset
        first = m.group(1).split(",")[0].strip().split(" ")[0]
        if first:
            found.append(html_lib.unescape(first))

    # Нормализуем (абсолютные http-ссылки на изображения), без дублей.
    seen = set()
    result: List[str] = []
    for u in found:
        u = (u or "").strip()
        if not u or u.startswith("data:"):
            continue
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = urljoin(base_url, u)
        if not u.startswith("http"):
            continue
        if not _is_image_url(u):
            continue
        if u in seen:
            continue
        seen.add(u)
        result.append(u)
        if len(result) >= _MAX_IMAGES:
            break
    return result


def _build_ai_text(html: str) -> str:
    """Собрать компактный текст для модели: мета + JSON-LD + видимый текст."""
    parts: List[str] = []
    title = _meta_content(html, "og:title")
    m_title = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    page_title = html_lib.unescape(m_title.group(1)).strip() if m_title else None
    desc = _meta_content(html, "og:description") or _meta_content(html, "description")
    if title:
        parts.append("Заголовок: " + title)
    elif page_title:
        parts.append("Заголовок: " + page_title)
    if desc:
        parts.append("Описание (мета): " + desc)
    jsonld = _jsonld_blocks(html)
    if jsonld:
        parts.append("Структурированные данные (JSON-LD):\n" + "\n".join(jsonld)[:4000])
    parts.append("Текст страницы:\n" + _visible_text(html))
    text = "\n\n".join(parts)
    return text[:_MAX_AI_CHARS]


def _fetch_listing(url: str) -> Tuple[str, List[str]]:
    """Загрузить страницу и вернуть (текст_для_AI, ссылки_на_фото)."""
    # Telegram-пост: текст и фото берём через уже готовый разбор встраивания.
    if photo_service._is_telegram_url(url):
        base = url.split("#")[0].split("?")[0]
        html, _ = _fetch_html(base + "?embed=1&mode=tme")
        images = photo_service._extract_image_urls(html)[:_MAX_IMAGES]
        return _build_ai_text(html), images

    html, final_url = _fetch_html(url)
    return _build_ai_text(html), _extract_images_generic(html, final_url)


# ── AI-извлечение полей ──────────────────────────────────────────────
def _ai_schema() -> dict:
    """JSON-схема ответа модели (строгий режим OpenAI)."""
    def nullable(types):
        return types + ["null"]

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": nullable(["string"])},
            "type": {"type": nullable(["string"]), "enum": OBJ_TYPE_VALUES + [None]},
            "district": {"type": nullable(["string"])},
            "address": {"type": nullable(["string"])},
            "rooms": {"type": nullable(["integer"])},
            "floor": {"type": nullable(["integer"])},
            "total_floors": {"type": nullable(["integer"])},
            "land_area": {"type": nullable(["number"])},
            "area": {"type": nullable(["number"])},
            "condition": {"type": nullable(["string"]), "enum": OBJ_COND_VALUES + [None]},
            "furniture_appliances": {"type": nullable(["string"]), "enum": FA_VALUES + [None]},
            "price": {"type": nullable(["number"])},
            "currency": {"type": nullable(["string"]), "enum": CURRENCIES + [None]},
            "owner_phone": {"type": nullable(["string"])},
            "description": {"type": nullable(["string"])},
        },
        "required": [
            "name", "type", "district", "address", "rooms", "floor", "total_floors",
            "land_area", "area", "condition", "furniture_appliances", "price",
            "currency", "owner_phone", "description",
        ],
    }


def _system_prompt(districts: List[str]) -> str:
    district_line = ", ".join(districts) if districts else "(список районов пуст)"
    return (
        "Ты — помощник агента недвижимости. Из текста объявления извлеки данные "
        "объекта и верни строго по схеме. Правила:\n"
        f"- type: выбери ближайшее из списка {OBJ_TYPE_VALUES}. Если объект — земельный "
        "участок, выбирай «Участок» (или «Земля»).\n"
        f"- Для типа «Земля»/«Участок» заполни land_area (площадь в сотках), а floor и "
        "total_floors оставь null. Для квартир/домов наоборот: floor/total_floors, а "
        "land_area = null.\n"
        f"- district: выбери из районов агентства, если явно совпадает: [{district_line}]. "
        "Если не совпадает — null, а район/местоположение впиши в address или description.\n"
        f"- condition: ближайшее из {OBJ_COND_VALUES} или null.\n"
        f"- furniture_appliances: одно из {FA_VALUES} (есть мебель и техника / только мебель "
        "/ только техника / ничего) или null.\n"
        "- price: только число без пробелов и валюты. currency: USD (доллары, $, у.е.), "
        "UZS (сум, сўм) или EUR (евро, €).\n"
        "- owner_phone: телефон из объявления, если есть.\n"
        "- description: на русском, кратко собери ВСЮ полезную информацию, которая не "
        "попала в отдельные поля (особенности, инфраструктура, условия и т.п.). Не "
        "выдумывай факты.\n"
        "- Чего в тексте нет — ставь null. Ничего не придумывай."
    )


def _extract_with_ai(text: str, districts: List[str]) -> dict:
    """Вызвать OpenAI и получить структурированные поля объекта."""
    if not settings.openai_api_key:
        raise AppError("import_ai_not_configured", status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key, timeout=40.0)
        resp = client.chat.completions.create(
            model=settings.import_ai_model,
            temperature=0,
            messages=[
                {"role": "system", "content": _system_prompt(districts)},
                {"role": "user", "content": "Текст объявления:\n\n" + text},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "listing", "strict": True, "schema": _ai_schema()},
            },
        )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Импорт: ошибка AI-разбора: %s", exc)
        raise AppError("import_ai_failed", status.HTTP_502_BAD_GATEWAY) from exc


# ── Пост-обработка ───────────────────────────────────────────────────
def _clean(data: dict) -> dict:
    """Подчистить ответ модели: типы, валюта, согласованность земли/этажей."""
    def s(v):
        v = (v or "").strip() if isinstance(v, str) else v
        return v or None

    out = {
        "name": s(data.get("name")),
        "type": s(data.get("type")),
        "district": s(data.get("district")),
        "address": s(data.get("address")),
        "rooms": data.get("rooms"),
        "floor": data.get("floor"),
        "total_floors": data.get("total_floors"),
        "land_area": data.get("land_area"),
        "area": data.get("area"),
        "condition": s(data.get("condition")),
        "furniture_appliances": s(data.get("furniture_appliances")),
        "price": data.get("price"),
        "currency": s(data.get("currency")),
        "owner_phone": s(data.get("owner_phone")),
        "description": s(data.get("description")),
    }
    # Валидируем по белым спискам (мусор → null).
    if out["type"] not in OBJ_TYPE_VALUES:
        out["type"] = None
    if out["condition"] not in OBJ_COND_VALUES:
        out["condition"] = None
    if out["furniture_appliances"] not in FA_VALUES:
        out["furniture_appliances"] = None
    if out["currency"] not in CURRENCIES:
        out["currency"] = None
    # Согласованность: участок — без этажей; иначе — без соток.
    if out["type"] in LAND_TYPES:
        out["floor"] = None
        out["total_floors"] = None
    else:
        out["land_area"] = None
    # Отрицательные числа отбрасываем.
    for k in ("rooms", "floor", "total_floors", "land_area", "area", "price"):
        v = out[k]
        if isinstance(v, (int, float)) and v < 0:
            out[k] = None
    return out


def import_preview(url: str, districts: List[str]) -> dict:
    """
    Главный вход: загрузить объявление, разобрать AI и вернуть поля + ссылки на
    фото + предупреждения. Ничего не сохраняет.
    """
    text, images = _fetch_listing(url)
    if not text or len(text.strip()) < 20:
        raise AppError("import_no_data", status.HTTP_400_BAD_REQUEST)

    fields = _clean(_extract_with_ai(text, districts))

    warnings: List[str] = []
    if not images:
        warnings.append("no_photos")
    has_any = any(v is not None for v in fields.values())
    if not has_any:
        warnings.append("few_fields")

    result = dict(fields)
    result["source_link"] = url
    result["photo_urls"] = images
    result["warnings"] = warnings
    return result
