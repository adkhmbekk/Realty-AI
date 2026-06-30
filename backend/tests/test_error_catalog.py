"""
Страж каталога ошибок: каждый код AppError("...") , который реально выбрасывается
в backend/app, обязан иметь перевод в errors.MESSAGES. Иначе пользователь увидит
сырой код (например "deal_not_found") вместо понятного текста на своём языке.

Этот тест ловит регрессию, из-за которой ранее «утекали» task_not_found,
deal_not_found, invalid_notify_pref и др.
"""
import re
from pathlib import Path

from app.core.errors import MESSAGES

_APP_DIR = Path(__file__).resolve().parents[1] / "app"
# Первый аргумент AppError(...) — это всегда строковый ключ сообщения.
_PAT = re.compile(r"""AppError\(\s*["'](\w+)["']""")


def test_all_apperror_codes_have_messages():
    missing: dict[str, str] = {}
    for path in _APP_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for code in _PAT.findall(text):
            if code not in MESSAGES:
                missing.setdefault(code, str(path.relative_to(_APP_DIR)))
    assert not missing, (
        "Коды AppError без перевода в errors.MESSAGES "
        f"(пользователь увидит сырой код): {missing}"
    )
