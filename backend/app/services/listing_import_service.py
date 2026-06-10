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
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from fastapi import status

from app.config import settings
from app.core.errors import AppError
from app.services import browser_render_service, photo_service

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


# Статика, которую не считаем фотографиями объекта (логотипы, аватары, иконки).
_NON_PHOTO_HINTS = (
    "logo", "avatar", "placeholder", "sprite", "icon", "favicon", "/flags/", "top-ten",
)


def _unwrap_proxy(u: str) -> str:
    """Развернуть Next.js-обёртку картинок: /_next/image?url=ENCODED&w=..&q=.."""
    try:
        parsed = urlparse(u)
        if parsed.path.endswith("/_next/image") or parsed.path == "/_next/image":
            inner = parse_qs(parsed.query).get("url", [None])[0]
            if inner:
                return unquote(inner)
    except Exception:  # noqa: BLE001
        pass
    return u


def _normalize_images(found: List[str], base_url: str) -> List[str]:
    """Привести список к абсолютным http-ссылкам на фото, без дублей и мусора."""
    seen = set()
    result: List[str] = []
    for u in found:
        u = (u or "").strip()
        if not u or u.startswith("data:"):
            continue
        u = _unwrap_proxy(u)
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = urljoin(base_url, u)
        if not u.startswith("http"):
            continue
        if not _is_image_url(u):
            continue
        low = u.lower()
        if any(h in low for h in _NON_PHOTO_HINTS):
            continue
        if u in seen:
            continue
        seen.add(u)
        result.append(u)
        if len(result) >= _MAX_IMAGES:
            break
    return result


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
    return _normalize_images(found, base_url)


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


# Мало осмысленного текста на странице → вероятно «одностраничник» (контент за JS).
_THIN_CONTENT_CHARS = 400


def _build_ai_text_from_rendered(html: str, rendered_text: str) -> str:
    """Собрать текст для AI из отрендеренной страницы (+ мета-теги, если были)."""
    head: List[str] = []
    if html:
        title = _meta_content(html, "og:title")
        desc = _meta_content(html, "og:description") or _meta_content(html, "description")
        if title:
            head.append("Заголовок: " + title)
        if desc:
            head.append("Описание (мета): " + desc)
    text = ("\n\n".join(head) + "\n\nТекст страницы:\n" + rendered_text).strip()
    return text[:_MAX_AI_CHARS]


def _fetch_listing(url: str) -> Tuple[str, List[str]]:
    """Загрузить страницу и вернуть (текст_для_AI, ссылки_на_фото)."""
    # Telegram-пост: текст и фото берём через уже готовый разбор встраивания.
    if photo_service._is_telegram_url(url):
        base = url.split("#")[0].split("?")[0]
        html, _ = _fetch_html(base + "?embed=1&mode=tme")
        images = photo_service._extract_image_urls(html)[:_MAX_IMAGES]
        return _build_ai_text(html), images

    # Быстрый путь: обычный HTTP. Для большинства сайтов этого достаточно.
    html, final_url = "", url
    try:
        html, final_url = _fetch_html(url)
    except AppError:
        html = ""  # не удалось — попробуем браузером ниже
    text = _build_ai_text(html) if html else ""
    images = _extract_images_generic(html, final_url) if html else []

    # Сайт-одностраничник (текста почти нет — он рисуется скриптами): добираем
    # настоящим браузером. Любая ошибка рендера → тихо остаёмся на HTTP-разборе.
    if len(_visible_text(html).strip() if html else "") < _THIN_CONTENT_CHARS:
        rendered = browser_render_service.try_render(url)
        if rendered:
            r_text, r_final, r_imgs = rendered
            if len((r_text or "").strip()) > len(_visible_text(html).strip() if html else ""):
                text = _build_ai_text_from_rendered(html, r_text)
                r_imgs_norm = _normalize_images(r_imgs, r_final)
                if r_imgs_norm:
                    images = r_imgs_norm

    return text, images


# ── AI-извлечение полей (Google Gemini) ──────────────────────────────
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _system_prompt(districts: List[str]) -> str:
    district_line = ", ".join(districts) if districts else "(список районов пуст)"
    return (
        "Ты — помощник агента недвижимости. Из текста объявления извлеки данные "
        "объекта. Правила:\n"
        "- Текст может быть на узбекском или русском — пойми смысл в любом случае.\n"
        "- В тексте может быть блок «похожие/рекомендованные объявления» (список "
        "других объектов с ценами). ИГНОРИРУЙ его — извлекай ТОЛЬКО основной "
        "объект (обычно он в начале страницы). Если основного объекта в тексте "
        "нет (например, объявление удалено) — верни все поля null.\n"
        f"- type: выбери РОВНО одно из списка {OBJ_TYPE_VALUES}. Если объект — земельный "
        "участок, выбирай «Участок» (или «Земля»).\n"
        "- Для типа «Земля»/«Участок» заполни land_area (площадь в сотках), а floor и "
        "total_floors оставь null. Для квартир/домов наоборот: floor/total_floors, а "
        "land_area = null.\n"
        f"- district: выбери из районов агентства, если явно совпадает: [{district_line}]. "
        "Если не совпадает — null, а район/местоположение впиши в address или description.\n"
        f"- condition: РОВНО одно из {OBJ_COND_VALUES} или null.\n"
        f"- furniture_appliances: РОВНО одно из {FA_VALUES} (есть мебель и техника / только "
        "мебель / только техника / ничего) или null.\n"
        "- price: только число без пробелов и валюты. currency: \"USD\" (доллары, $, у.е.), "
        "\"UZS\" (сум, сўм) или \"EUR\" (евро, €).\n"
        "- owner_phone: телефон из объявления, если есть.\n"
        "- description: на русском, кратко собери ВСЮ полезную информацию, которая не "
        "попала в отдельные поля (особенности, инфраструктура, условия и т.п.). Не "
        "выдумывай факты.\n"
        "- Чего в тексте нет — ставь null. Ничего не придумывай.\n\n"
        "Верни ТОЛЬКО JSON-объект (без пояснений) с ключами: name (строка), type (строка), "
        "district (строка), address (строка), rooms (целое), floor (целое), total_floors "
        "(целое), land_area (число), area (число), condition (строка), furniture_appliances "
        "(строка), price (число), currency (строка), owner_phone (строка), description "
        "(строка). Любое неизвестное значение — null."
    )


def _extract_with_ai(text: str, districts: List[str]) -> dict:
    """Вызвать Google Gemini и получить структурированные поля объекта."""
    if not settings.gemini_api_key:
        raise AppError("import_ai_not_configured", status.HTTP_503_SERVICE_UNAVAILABLE)

    url = _GEMINI_URL.format(model=settings.import_ai_model)
    payload = {
        "system_instruction": {"parts": [{"text": _system_prompt(districts)}]},
        "contents": [{"role": "user", "parts": [{"text": "Текст объявления:\n\n" + text}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    try:
        resp = httpx.post(
            url, params={"key": settings.gemini_api_key}, json=payload, timeout=45.0
        )
        resp.raise_for_status()
        data = resp.json()
        cands = data.get("candidates") or []
        if not cands:
            raise AppError("import_ai_failed", status.HTTP_502_BAD_GATEWAY)
        parts = (cands[0].get("content") or {}).get("parts") or []
        content = "".join(p.get("text", "") for p in parts).strip() or "{}"
        return json.loads(content)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Импорт: ошибка AI-разбора (Gemini): %s", exc)
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


def extract_fields_from_text(text: str, districts: List[str]) -> dict:
    """
    Извлечь поля объекта из ГОТОВОГО текста (без загрузки страницы) — для
    массового импорта из Telegram-канала, где текст постов уже получен. Возвращает
    тот же набор очищенных полей, что и import_preview (без фото и предупреждений).
    """
    if not text or len(text.strip()) < 20:
        return _clean({})
    return _clean(_extract_with_ai(text, districts))


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
