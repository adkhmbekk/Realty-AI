"""
Тест защиты от случайного массового удаления через Google-таблицу
(_is_mass_deletion). Чистая функция, без сети.
"""
from app.services.sheets_service import _is_mass_deletion


def test_small_deletions_allowed():
    # Удаление нескольких объектов — норма, не блокируем.
    assert _is_mass_deletion(1, 100) is False
    assert _is_mass_deletion(4, 100) is False
    # Меньше порога по абсолютному числу — всегда разрешено.
    assert _is_mass_deletion(4, 4) is False


def test_mass_deletion_blocked():
    # Снесли всю/бОльшую часть базы — блокируем.
    assert _is_mass_deletion(100, 100) is True
    assert _is_mass_deletion(60, 100) is True
    assert _is_mass_deletion(10, 20) is True


def test_large_base_partial_cleanup_allowed():
    # Большая база, удалили малую долю (10%) — это легитимная чистка.
    assert _is_mass_deletion(100, 1000) is False
