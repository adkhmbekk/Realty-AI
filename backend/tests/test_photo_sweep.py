"""
Тест безопасности подчистки осиротевших файлов фото (M4).

Проверяем САМОЕ ВАЖНОЕ: функция удаляет ТОЛЬКО файлы без строки в БД И старше
grace-периода. Файлы, у которых есть строка в БД, и свежие файлы — не трогает.
"""
import os
import time

from app.config import settings
from app.repositories import apartment_photo_repo
from app.services import photo_service


def test_sweep_removes_only_old_orphans(tmp_path, monkeypatch):
    d = tmp_path / "photos"
    d.mkdir()
    monkeypatch.setattr(settings, "photos_dir", str(d))

    (d / "known_key").write_bytes(b"x")      # есть строка в БД
    (d / "recent_orphan").write_bytes(b"x")  # сирота, но свежий
    old = d / "old_orphan"                    # сирота и старый → под удаление
    old.write_bytes(b"x")
    past = time.time() - 48 * 3600
    os.utime(old, (past, past))

    monkeypatch.setattr(apartment_photo_repo, "all_storage_keys", lambda _db: ["known_key"])

    removed = photo_service.sweep_orphan_photos(db=None, grace_hours=24)

    assert removed == 1
    assert (d / "known_key").exists(), "файл с записью в БД не должен удаляться"
    assert (d / "recent_orphan").exists(), "свежий файл не должен удаляться"
    assert not old.exists(), "старый осиротевший файл должен быть удалён"


def test_sweep_noop_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "photos_dir", str(tmp_path / "nope"))
    monkeypatch.setattr(apartment_photo_repo, "all_storage_keys", lambda _db: [])
    assert photo_service.sweep_orphan_photos(db=None) == 0
