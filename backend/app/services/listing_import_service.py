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
import time
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from fastapi import status

from app.config import settings
from app.core import ssrf
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
DEAL_TYPE_VALUES = ["sale", "rent"]
RENT_PERIOD_VALUES = ["month", "day"]
LAND_TYPES = ("Земля", "Участок")
# Типы с земельным участком (дом тоже): «Этаж» (floor) не заполняем; «Этажность»
# (total_floors) и «Соток» (land_area) — заполняем. Зеркало фронта (hasLandArea).
LAND_AREA_TYPES = ("Дом", "Земля", "Участок")

# Ограничения, чтобы не раздувать память/токены.
_MAX_HTML_BYTES = 3 * 1024 * 1024     # не качаем гигантские страницы
_MAX_AI_CHARS = 14_000               # сколько текста отдаём модели
_MAX_IMAGES = 20                     # сколько ссылок на фото возвращаем
_MAX_REDIRECTS = 5                   # сколько переходов по Location допускаем
_FETCH_TIMEOUT = httpx.Timeout(12.0, connect=8.0)


# ── Загрузка страницы ────────────────────────────────────────────────
def _fetch_html(url: str) -> Tuple[str, str]:
    """
    Скачать HTML страницы. Возвращает (html, final_url).

    Защита от SSRF: редиректы НЕ следуем автоматически (иначе публичная страница
    могла бы 302-редиректом увести нас на внутренний адрес). Идём по Location
    вручную и проверяем _assert_public_url на КАЖДОМ переходе — как в
    photo_service._afetch.
    """
    current = url
    try:
        with httpx.Client(
            transport=ssrf.sync_transport(), follow_redirects=False, timeout=_FETCH_TIMEOUT
        ) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                # бросит AppError при внутреннем/непубличном адресе
                photo_service._assert_public_url(current)
                with client.stream(
                    "GET", current,
                    headers={
                        "User-Agent": photo_service._UA,
                        "Accept": "text/html,application/xhtml+xml,*/*",
                        "Accept-Language": "ru,en;q=0.8",
                    },
                ) as resp:
                    if 300 <= resp.status_code < 400:
                        loc = resp.headers.get("Location")
                        if not loc:
                            raise AppError(
                                "import_fetch_failed", status.HTTP_400_BAD_REQUEST
                            )
                        # следующий хоп проверим в начале цикла (urljoin — на
                        # случай относительного Location)
                        current = urljoin(current, loc)
                        continue
                    if resp.status_code >= 400:
                        raise AppError(
                            "import_fetch_failed", status.HTTP_400_BAD_REQUEST
                        )
                    chunks: List[bytes] = []
                    total = 0
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if total > _MAX_HTML_BYTES:
                            break
                        chunks.append(chunk)
                    final_url = str(resp.url)
                    return b"".join(chunks).decode("utf-8", errors="ignore"), final_url
            # слишком много редиректов
            raise AppError("import_fetch_failed", status.HTTP_400_BAD_REQUEST)
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

    # ВАЖНО (SSRF): проверяем адрес ДО любой загрузки, чтобы это покрыло и
    # запасной путь через браузер ниже. Иначе file:// или внутренний http
    # дошли бы до Playwright (который сам адрес не проверяет) и прочитали бы
    # локальные файлы/внутренние сервисы. Внутренний адрес → сразу AppError.
    photo_service._assert_public_url(url)

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
        "- deal_type: 'rent' если это АРЕНДА/СДАЧА (аренда, сдаётся, сдаю, сдам, "
        "ижара, ijara, ijaraga beriladi, arendaga, oylik/oyiga, kunlik/kuniga, "
        "посуточно, на длительный срок); 'sale' если ПРОДАЖА (продаётся, продаю, "
        "продам, sotiladi, sotuvga). Если явно не указано — 'sale'.\n"
        "- rent_period: ТОЛЬКО для аренды — 'day' если посуточно/на сутки (kunlik, "
        "kuniga, сутки, посуточно), иначе 'month' (помесячно, oylik, в месяц, за "
        "месяц). Для продажи rent_period = null.\n"
        "- Цена при аренде (price) — это арендная ставка (за месяц или за сутки), "
        "как указано в объявлении; правило «цена за м²» к аренде не применяй.\n"
        f"- type: выбери РОВНО одно из списка {OBJ_TYPE_VALUES}. Если объект — земельный "
        "участок, выбирай «Участок» (или «Земля»).\n"
        "- Для типа «Дом», «Земля» или «Участок» заполни land_area (площадь в сотках) "
        "и НЕ заполняй floor (этаж) — оставь null; total_floors (этажность дома) можно "
        "заполнить. Для квартиры/коммерции наоборот: floor и total_floors, а land_area = null.\n"
        "- ВАЖНО: комнаты/этаж/этажность часто пишут вместе через дробь или дефис. "
        "Три числа «5/9/16» = rooms(5)/floor(9)/total_floors(16). Два числа «9/16» "
        "(когда комнаты указаны отдельно) = floor(9)/total_floors(16). Обязательно "
        "разложи такие записи по полям rooms/floor/total_floors. Не оставляй их пустыми, "
        "если в тексте есть такая дробь.\n"
        f"- district: выбери из районов агентства, если явно совпадает: [{district_line}]. "
        "Если не совпадает — null, а район/местоположение впиши в address или description.\n"
        f"- condition: РОВНО одно из {OBJ_COND_VALUES} или null.\n"
        f"- furniture_appliances: РОВНО одно из {FA_VALUES} (есть мебель и техника / только "
        "мебель / только техника / ничего) или null.\n"
        "- price: ТОЛЬКО полная цена всего объекта — число без пробелов и валюты. "
        "ВАЖНО: если в тексте указана цена ЗА КВАДРАТНЫЙ МЕТР (например «1200 $/м²», "
        "«за квадрат», «за 1 кв.м», «1 kv.m narxi»), а НЕ полная стоимость объекта — "
        "оставь price = null, а саму цену за м² впиши в description (например "
        "«Цена за м²: 1200 $»). В price попадает только полная цена объекта целиком.\n"
        "- currency: \"USD\" (доллары, $, у.е.), \"UZS\" (сум, сўм) или \"EUR\" (евро, €).\n"
        "- owner_phone: ВСЕ телефонные номера из объявления. Если номеров несколько — "
        "перечисли их все через перенос строки. Только сюда попадают номера.\n"
        "- description: на русском, кратко собери ВСЮ полезную информацию, которая не "
        "попала в отдельные поля (особенности, инфраструктура, условия и т.п.). "
        "КАТЕГОРИЧЕСКИ НЕ включай сюда телефонные номера и контакты — они идут только в "
        "owner_phone. Не выдумывай факты.\n"
        "- Чего в тексте нет — ставь null. Ничего не придумывай.\n\n"
        "Верни ТОЛЬКО JSON-объект (без пояснений) с ключами: deal_type (строка 'sale'/'rent'), "
        "rent_period (строка 'month'/'day' или null), name (строка), type (строка), "
        "district (строка), address (строка), rooms (целое), floor (целое), total_floors "
        "(целое), land_area (число), area (число), condition (строка), furniture_appliances "
        "(строка), price (число), currency (строка), owner_phone (строка), description "
        "(строка). Любое неизвестное значение — null."
    )


# Паузы (сек) перед повторными попытками к ИИ.
#  - 429/503 (лимит частоты / перегрузка Gemini): ЖДЁМ Gemini — он основной и
#    оплачен. Бэкофф короткий и ограниченный, чтобы ОДИН запрос массового импорта
#    не висел дольше таймаута; «подождать подольше» обеспечивает пауза-и-повтор на
#    фронте (он переспрашивает тот же пост позже). На запасной (OpenRouter) уходим
#    ТОЛЬКО при 429 (лимит/кончились деньги); на 503 (перегрузка) — ждём Gemini.
#  - сетевой сбой/DNS (ConnectError — грабли Docker/WSL): короткий повтор.
_BACKOFF_RETRY = (3, 8)
_BACKOFF_NET = (1.5, 4)


def _retry_after_seconds(resp: "httpx.Response", default: float) -> float:
    """Сколько ждать перед повтором: из заголовка Retry-After, иначе default."""
    ra = resp.headers.get("Retry-After")
    if ra:
        try:
            return min(float(ra), 30.0)
        except ValueError:
            pass
    return default


_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _post_with_retry(url, *, headers=None, params=None, json_body=None, timeout=45.0):
    """POST с повторами — общий для Gemini и OpenRouter. На 429/503 (лимит/перегрузка)
    терпеливо повторяем (Gemini основной и оплачен — ждём его), но КОРОТКО, чтобы
    один запрос массового импорта не висел дольше таймаута. Исчерпав повторы, бросаем
    import_ai_rate_limited С ИСХОДНЫМ кодом (429 или 503): выше (_extract_with_ai)
    503 = ждать Gemini (не уходить на запасной), 429 = можно уйти на запасной. На
    сетевой сбой/DNS (ConnectError, Docker/WSL) — короткий повтор. Возвращает Response."""
    attempt = 0
    while True:
        try:
            resp = httpx.post(url, headers=headers, params=params, json=json_body, timeout=timeout)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # Не удалось установить соединение (часто — кратковременный сбой DNS
            # встроенного резолвера Docker/WSL). Коротко ждём и повторяем.
            if attempt < len(_BACKOFF_NET):
                time.sleep(_BACKOFF_NET[attempt])
                attempt += 1
                continue
            raise AppError("import_ai_failed", status.HTTP_502_BAD_GATEWAY) from exc
        if resp.status_code in (429, 503):
            if attempt < len(_BACKOFF_RETRY):
                time.sleep(_retry_after_seconds(resp, _BACKOFF_RETRY[attempt]))
                attempt += 1
                continue
            # Повторы исчерпаны. Код СОХРАНЯЕМ (429/503) — по нему вызывающий решает,
            # ждать Gemini (503) или уйти на запасного провайдера (429).
            raise AppError("import_ai_rate_limited", resp.status_code)
        resp.raise_for_status()
        return resp


def _loads_ai_json(content: str) -> dict:
    """Распарсить JSON из ответа модели. Бесплатные модели иногда оборачивают JSON
    в ```json ... ``` или добавляют текст — снимаем обёртку и выдираем {…}."""
    content = (content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\s*", "", content)
        content = re.sub(r"\s*```$", "", content).strip()
    try:
        return json.loads(content or "{}")
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


def _extract_gemini(text: str, districts: List[str], model: str) -> dict:
    """Извлечь поля через Google Gemini (REST)."""
    if not settings.gemini_api_key:
        raise AppError("import_ai_not_configured", status.HTTP_503_SERVICE_UNAVAILABLE)
    url = _GEMINI_URL.format(model=model or settings.import_ai_model)
    payload = {
        "system_instruction": {"parts": [{"text": _system_prompt(districts)}]},
        "contents": [{"role": "user", "parts": [{"text": "Текст объявления:\n\n" + text}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    resp = _post_with_retry(url, params={"key": settings.gemini_api_key}, json_body=payload)
    data = resp.json()
    cands = data.get("candidates") or []
    if not cands:
        raise AppError("import_ai_failed", status.HTTP_502_BAD_GATEWAY)
    parts = (cands[0].get("content") or {}).get("parts") or []
    content = "".join(p.get("text", "") for p in parts).strip() or "{}"
    return _loads_ai_json(content)


def _extract_openrouter(text: str, districts: List[str], model: str) -> dict:
    """Извлечь поля через OpenRouter (OpenAI-совместимый API). Бесплатная
    подстраховка / основной провайдер, когда у Gemini нет денег/лимита."""
    if not settings.openrouter_api_key:
        raise AppError("import_ai_not_configured", status.HTTP_503_SERVICE_UNAVAILABLE)
    payload = {
        "model": model or settings.openrouter_model,
        "messages": [
            {"role": "system", "content": _system_prompt(districts)},
            {"role": "user", "content": "Текст объявления:\n\n" + text},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        # OpenRouter просит указывать источник (необязательно, для аналитики).
        "HTTP-Referer": settings.public_base_url,
        "X-Title": "Realty-AI",
    }
    resp = _post_with_retry(_OPENROUTER_URL, headers=headers, json_body=payload, timeout=60.0)
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise AppError("import_ai_failed", status.HTTP_502_BAD_GATEWAY)
    content = (choices[0].get("message") or {}).get("content") or ""
    return _loads_ai_json(content)


_AI_PROVIDERS = {"gemini": _extract_gemini, "openrouter": _extract_openrouter}


def _provider_order() -> List[str]:
    """Порядок провайдеров из settings.import_ai_providers — только настроенные
    (с ключом). Напр. 'openrouter' (Gemini без денег) или 'gemini,openrouter'."""
    order: List[str] = []
    for p in (settings.import_ai_providers or "").split(","):
        p = p.strip().lower()
        if p in order or p not in _AI_PROVIDERS:
            continue
        if p == "gemini" and not settings.gemini_api_key:
            continue
        if p == "openrouter" and not settings.openrouter_api_key:
            continue
        order.append(p)
    return order


# Бесплатные модели НЕСТАБИЛЬНЫ: один и тот же текст то разбирается верно, то
# отдаёт мусор (невалидный JSON) или пусто (все поля null) — даже при
# temperature=0. Поэтому при «мягком» сбое (ошибка разбора ИЛИ пустой результат)
# повторяем запрос несколько раз — это резко поднимает долю успешных разборов.
_AI_SOFT_RETRIES = 2


def _is_empty_result(data: dict) -> bool:
    """Валидный JSON, но модель ничего не извлекла (все поля пустые).

    deal_type/rent_period НЕ считаем значимыми: модель часто ставит deal_type='sale'
    по умолчанию даже для мусора — иначе пустой результат не распознавался бы."""
    if not data:
        return True
    return not any(
        v not in (None, "", [], {})
        for k, v in data.items()
        if k not in ("deal_type", "rent_period")
    )


def _extract_with_ai(text: str, districts: List[str], model: Optional[str] = None) -> dict:
    """Извлечь поля объекта через ИИ. Пробуем провайдеров по порядку
    (settings.import_ai_providers). Gemini основной и оплачен: на его временную
    ПЕРЕГРУЗКУ (503) НЕ уходим на запасной, а тормозим (массовый импорт сделает
    паузу и повторит этот пост на Gemini). На запасной (OpenRouter) уходим только
    при 429 (лимит частоты / у Gemini кончились деньги). На «мягкий» сбой
    (мусор/пусто) повторяем тот же провайдер до _AI_SOFT_RETRIES раз."""
    order = _provider_order()
    if not order:
        raise AppError("import_ai_not_configured", status.HTTP_503_SERVICE_UNAVAILABLE)
    rate_limited = False
    overloaded = False  # Gemini вернул 503 (перегрузка) — ждём его, не уходим на запасной
    for prov in order:
        for attempt in range(_AI_SOFT_RETRIES + 1):
            try:
                if prov == "gemini":
                    data = _extract_gemini(text, districts, model or settings.import_ai_model)
                else:
                    data = _extract_openrouter(text, districts, settings.openrouter_model)
            except AppError as exc:
                # 503 у Gemini — временная перегрузка модели. Gemini оплачен и
                # основной, поэтому НЕ уходим на запасной: ждём Gemini (пауза-повтор).
                if prov == "gemini" and exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
                    overloaded = True
                    break
                if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                    rate_limited = True
                    break  # лимит / кончились деньги — можно к следующему провайдеру
                logger.info("Импорт: %s сбой разбора (%s), попытка %d",
                            prov, exc.status_code, attempt + 1)
                continue  # мусорный ответ модели — повторим
            except Exception as exc:  # noqa: BLE001
                logger.warning("Импорт: %s сбой разбора: %s (попытка %d)", prov, exc, attempt + 1)
                continue
            # HTTP/JSON ок. Если пусто — возможно, флапнула бесплатная модель:
            # повторяем; на последней попытке отдаём как есть (это нормальный
            # «не объявление», его отсеют выше по структурным полям).
            if _is_empty_result(data) and attempt < _AI_SOFT_RETRIES:
                logger.info("Импорт: %s вернул пусто, повтор %d", prov, attempt + 1)
                continue
            return data
        # Перегрузка Gemini (503): НЕ уходим на запасной — ждём Gemini. Тормозим
        # массовый импорт (фронт сделает паузу и повторит этот пост позже). На
        # запасной (OpenRouter) уходим только при 429 — это следующий провайдер.
        if prov == "gemini" and overloaded:
            raise AppError("import_ai_rate_limited", status.HTTP_429_TOO_MANY_REQUESTS)
        # провайдер исчерпал попытки — пробуем следующего
    # Никто не справился. 429 (лимит частоты) пробрасываем отдельно — массовый
    # импорт по нему делает паузу и повторяет позже, а не помечает пост ошибкой.
    raise AppError(
        "import_ai_rate_limited" if rate_limited else "import_ai_failed",
        status.HTTP_429_TOO_MANY_REQUESTS if rate_limited else status.HTTP_502_BAD_GATEWAY,
    )


# ── Пост-обработка ───────────────────────────────────────────────────
# ── Приватность: телефоны собственника — ТОЛЬКО в поле owner_phone ─────
# Токен-кандидат в телефон: цифра, затем 6+ символов из цифр/разделителей, затем цифра.
_PHONE_TOKEN_RE = re.compile(r"\+?\d[\d\s()\-–.]{5,}\d")
# Коды мобильных операторов Узбекистана (первые 2 цифры 9-значного номера).
_UZ_MOBILE_CODES = {"90", "91", "93", "94", "95", "97", "98", "99", "88", "77", "33", "20"}
# Что идёт СРАЗУ после числа и делает его ценой/площадью, а не телефоном.
_PRICE_UNIT_RE = re.compile(
    r"^\s*(сум|со['ʻ]?м|so[’'ʻ]?m|uzs|у\.?\s?е|y\.?\s?e|\$|usd|доллар|евро|eur|€|млн|млрд|"
    r"м2|м²|кв|соток|сот\b)",
    re.I,
)


def _digits(s: Optional[str]) -> str:
    return re.sub(r"\D", "", s or "")


def _is_phone(raw: str, digits: str, after: str, lenient: bool) -> bool:
    # Число, за которым сразу валюта/площадь — это цена, не телефон.
    if _PRICE_UNIT_RE.match(after or ""):
        return False
    if raw.lstrip().startswith("+"):
        return 9 <= len(digits) <= 15
    if len(digits) == 12 and digits.startswith("998"):
        return True
    if len(digits) == 9 and digits[:2] in _UZ_MOBILE_CODES:
        return True
    # Явная телефонная группировка дефисами: XX-XXX-XX-XX. Чтобы НЕ принять за
    # телефон кадастровые/документные номера (например 12-34-567-89-01 — 4 группы,
    # 11 цифр, часто с ':'), сужаем: не более 3 дефисов, без ':', телефонная длина
    # (9–12 цифр), а 12 цифр обязаны начинаться на 998 (BL2).
    dashes = raw.count("-") + raw.count("–")
    if ":" not in raw and 2 <= dashes <= 3 and 9 <= len(digits) <= 12:
        if len(digits) == 12 and not digits.startswith("998"):
            return False
        return True
    # В owner_phone (модель уже назвала это телефоном) — мягче.
    if lenient and 7 <= len(digits) <= 15:
        return True
    return False


def strip_phones(text: Optional[str]) -> Optional[str]:
    """Вернуть текст БЕЗ телефонных номеров — жёсткое затирание контактов
    собственника в свободных полях общей базы (MLS). Та же валидация, что и при
    импорте (цены/площади за телефон не считаются)."""
    _, cleaned = _pull_phones(text, lenient=False)
    return cleaned


def _pull_phones(text: Optional[str], lenient: bool = False) -> Tuple[List[str], Optional[str]]:
    """Достать телефоны из текста; вернуть (номера, текст-без-номеров)."""
    if not text:
        return [], text
    phones: List[str] = []
    parts: List[str] = []
    last = 0
    for m in _PHONE_TOKEN_RE.finditer(text):
        d = _digits(m.group(0))
        after = text[m.end():m.end() + 6]
        if _is_phone(m.group(0), d, after, lenient):
            phones.append(m.group(0).strip(" .,-–()"))
            parts.append(text[last:m.start()])
            last = m.end()
    parts.append(text[last:])
    cleaned = "".join(parts)
    # Осиротевшие метки «тел:/контакт:» и лишние разделители.
    cleaned = re.sub(r"(?i)\b(тел(ефон)?|контакт|phone|моб(ил)?|aloqa|tel)\.?\s*[:№]?\s*", " ", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"([,;:]\s*){2,}", ", ", cleaned)
    return phones, (cleaned.strip(" ,;:-–\n") or None)


def _sanitize_phones(out: dict) -> dict:
    """Гарантия приватности: ВСЕ номера — только в owner_phone (до 5), а из
    описания/адреса/названия они вырезаны. Дедуп по цифрам."""
    collected: List[str] = []
    if out.get("owner_phone"):
        ph, _ = _pull_phones(out["owner_phone"], lenient=True)
        collected.extend(ph)
    for field in ("description", "address", "name"):
        val = out.get(field)
        if not val:
            continue
        ph, cleaned = _pull_phones(val, lenient=False)
        if ph:
            collected.extend(ph)
            out[field] = cleaned
    seen: set = set()
    uniq: List[str] = []
    for p in collected:
        key = _digits(p)
        if len(key) < 7 or key in seen:
            continue
        seen.add(key)
        uniq.append(p)
        if len(uniq) >= 5:
            break
    out["owner_phone"] = "\n".join(uniq) if uniq else None
    return out


def _clean(data: dict) -> dict:
    """Подчистить ответ модели: типы, валюта, согласованность земли/этажей."""
    def s(v):
        v = (v or "").strip() if isinstance(v, str) else v
        return v or None

    out = {
        "deal_type": s(data.get("deal_type")),
        "rent_period": s(data.get("rent_period")),
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
    # Тип сделки: что не 'rent' — то продажа (безопасное значение по умолчанию).
    out["deal_type"] = "rent" if out["deal_type"] == "rent" else "sale"
    # Срок аренды — только для аренды; иначе null. Непонятное у аренды → 'month'.
    if out["deal_type"] == "rent":
        out["rent_period"] = out["rent_period"] if out["rent_period"] in RENT_PERIOD_VALUES else "month"
    else:
        out["rent_period"] = None
    # Валидируем по белым спискам (мусор → null).
    if out["type"] not in OBJ_TYPE_VALUES:
        out["type"] = None
    if out["condition"] not in OBJ_COND_VALUES:
        out["condition"] = None
    if out["furniture_appliances"] not in FA_VALUES:
        out["furniture_appliances"] = None
    if out["currency"] not in CURRENCIES:
        out["currency"] = None
    # Согласованность: дом/участок/земля — без «Этажа» (но «Этажность» остаётся);
    # квартира/коммерция — без «Соток».
    if out["type"] in LAND_AREA_TYPES:
        out["floor"] = None
    else:
        out["land_area"] = None
    # Отрицательные числа отбрасываем.
    for k in ("rooms", "floor", "total_floors", "land_area", "area", "price"):
        v = out[k]
        if isinstance(v, (int, float)) and v < 0:
            out[k] = None
    # Приватность: номера собственника — только в owner_phone, не в описании и пр.
    return _sanitize_phones(out)


def extract_fields_from_text(text: str, districts: List[str]) -> dict:
    """
    Извлечь поля объекта из ГОТОВОГО текста (без загрузки страницы) — для
    массового импорта из Telegram-канала, где текст постов уже получен. Возвращает
    тот же набор очищенных полей, что и import_preview (без фото и предупреждений).
    """
    if not text or len(text.strip()) < 20:
        return _clean({})
    # Массовый/фоновый импорт — на более дешёвой модели (flash-lite).
    return _clean(_extract_with_ai(text, districts, model=settings.import_ai_model_bulk))


def derive_source_from_url(url: str) -> Optional[str]:
    """
    «Источник» из ссылки — в том же виде, что и массовый импорт из Telegram
    (telegram_channel_service пишет source="@канал"). Для t.me/telegram.me
    возвращаем "@имя_канала"; для прочих площадок — домен (например "olx.uz").
    Приватные ссылки (t.me/c/…, t.me/+…) источника не дают.
    """
    try:
        u = urlparse(url)
        host = (u.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if host in ("t.me", "telegram.me"):
            parts = [p for p in u.path.split("/") if p]
            # t.me/s/<канал>/<пост> — веб-превью канала.
            if parts and parts[0] == "s":
                parts = parts[1:]
            if not parts:
                return None
            name = parts[0]
            if name in ("c", "joinchat") or name.startswith("+"):
                return None
            return f"@{name}"
        return host or None
    except Exception:  # noqa: BLE001
        return None


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
    # deal_type всегда заполнен ('sale' по умолчанию) — для оценки «мало данных»
    # его и срок аренды не учитываем.
    has_any = any(
        v is not None for k, v in fields.items() if k not in ("deal_type", "rent_period")
    )
    if not has_any:
        warnings.append("few_fields")

    result = dict(fields)
    result["source_link"] = url
    # Источник (название канала/площадки) — как в массовом импорте.
    result["source"] = derive_source_from_url(url)
    result["photo_urls"] = images
    result["warnings"] = warnings
    return result
