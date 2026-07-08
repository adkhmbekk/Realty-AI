"""
Абстракция хранилища фотографий.

Зачем: сейчас фото лежат файлами на диске (LocalDiskStorage). В будущем
планируется арендовать S3 и переехать туда — для этого достаточно добавить
класс S3Storage и переключить `PHOTO_STORAGE_BACKEND` в конфиге. Остальной код
работает через единый интерфейс `Storage` и не зависит от того, где лежат файлы.

ВАЖНО (стабильные ссылки): публичная ссылка на фото всегда имеет вид
`/api/v1/photos/<ключ>` и НЕ зависит от бэкенда. Эндпоинт отдачи читает файл из
текущего хранилища. Поэтому переезд на S3 не ломает ранее выданные ссылки —
в том числе те, что уже записаны в Google-таблицы клиентов.
"""
import os
from typing import List, Optional, Protocol, runtime_checkable

from app.config import settings


@runtime_checkable
class Storage(Protocol):
    """Единый интерфейс хранилища бинарных файлов по строковому ключу."""

    def save(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> Optional[bytes]: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def list_keys(self) -> List[str]: ...
    # Локальный путь к файлу — только для дискового бэкенда (быстрая отдача
    # через FileResponse). Для S3 вернёт None, и отдача пойдёт чтением байтов.
    def local_path(self, key: str) -> Optional[str]: ...
    def mtime(self, key: str) -> Optional[float]: ...


class LocalDiskStorage:
    """Хранилище на локальном диске (текущий бэкенд)."""

    @property
    def base_dir(self) -> str:
        # Читаем путь из настроек динамически (а не фиксируем при создании) —
        # так уважается переопределение PHOTOS_DIR и упрощается тестирование.
        return settings.photos_dir

    def _path(self, key: str) -> str:
        return os.path.join(self.base_dir, key)

    def _ensure(self) -> None:
        os.makedirs(self.base_dir, exist_ok=True)

    def save(self, key: str, data: bytes) -> None:
        self._ensure()
        with open(self._path(key), "wb") as f:
            f.write(data)

    def read(self, key: str) -> Optional[bytes]:
        try:
            with open(self._path(key), "rb") as f:
                return f.read()
        except OSError:
            return None

    def exists(self, key: str) -> bool:
        return os.path.isfile(self._path(key))

    def delete(self, key: str) -> None:
        try:
            os.remove(self._path(key))
        except OSError:
            pass

    def list_keys(self) -> List[str]:
        d = self.base_dir
        if not os.path.isdir(d):
            return []
        return [n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n))]

    def local_path(self, key: str) -> Optional[str]:
        p = self._path(key)
        return p if os.path.exists(p) else None

    def mtime(self, key: str) -> Optional[float]:
        try:
            return os.path.getmtime(self._path(key))
        except OSError:
            return None


def _build_storage() -> Storage:
    # Будущее: при photo_storage_backend == "s3" вернуть S3Storage(...) —
    # переезд на S3 без правок остального кода (ссылки на фото стабильны).
    return LocalDiskStorage()


# Единый экземпляр хранилища, который использует весь код (photo_service и др.).
storage: Storage = _build_storage()
