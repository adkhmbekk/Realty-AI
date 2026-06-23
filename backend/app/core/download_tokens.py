"""
Одноразовые короткоживущие коды для публичного скачивания (экспорт в Excel).

Зачем: ссылку на файл открывает ВНЕШНИЙ браузер (внутри Telegram скачать нельзя),
поэтому авторизационный заголовок туда не передать. Раньше в URL клали JWT — а он
утекает в логи ngrok/историю браузера/скриншоты и действует как обычный токен.
Теперь в URL — случайный одноразовый код: живёт несколько минут и срабатывает
ОДИН раз. Сам код ничего не «несёт» (просто ключ к серверной записи), поэтому его
утечка после скачивания бесполезна.

Хранилище — в памяти процесса (бэкенд запущен одним воркером uvicorn). При
перезапуске невыданные коды теряются — для 5-минутных ссылок это не проблема.
"""
import secrets
import threading
import time
from typing import Dict, Optional, Tuple

_TTL_SECONDS = 300  # 5 минут
_lock = threading.Lock()
# код -> (agency_id, время_истечения)
_store: Dict[str, Tuple[int, float]] = {}


def issue(agency_id: int) -> str:
    """Выдать одноразовый код скачивания для агентства."""
    code = secrets.token_urlsafe(32)
    now = time.time()
    with _lock:
        # попутно чистим протухшие, чтобы словарь не рос
        for c in [c for c, (_, exp) in _store.items() if exp < now]:
            _store.pop(c, None)
        _store[code] = (agency_id, now + _TTL_SECONDS)
    return code


def consume(code: str) -> Optional[int]:
    """Проверить и ПОГАСИТЬ код (одноразовый). Возвращает agency_id или None."""
    if not code:
        return None
    with _lock:
        item = _store.pop(code, None)  # одноразовость: удаляем при первом обращении
    if item is None:
        return None
    agency_id, exp = item
    if exp < time.time():
        return None
    return agency_id
