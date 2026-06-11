"""
Тесты массового импорта из Telegram-канала (Этап 3.1): нормализация имени канала
и разбор HTML ленты в посты. Сеть и ИИ здесь НЕ вызываются.
"""
import pytest

from app.core.errors import AppError
from app.services import telegram_channel_service as tg


def test_normalize_channel_variants():
    assert tg.normalize_channel("@my_channel") == "my_channel"
    assert tg.normalize_channel("https://t.me/my_channel") == "my_channel"
    assert tg.normalize_channel("https://t.me/s/my_channel") == "my_channel"
    assert tg.normalize_channel("t.me/my_channel/123") == "my_channel"
    assert tg.normalize_channel("my_channel") == "my_channel"


def test_normalize_channel_rejects_garbage():
    for bad in ("", "  ", "@@", "a b c", "ab"):
        with pytest.raises(AppError):
            tg.normalize_channel(bad)


_FEED_HTML = """
<div class="tgme_widget_message_wrap js-widget_message_wrap">
  <div class="tgme_widget_message" data-post="realty/101">
    <a class="tgme_widget_message_photo_wrap"
       style="background-image:url('https://cdn.telegram-cdn.org/file/a.jpg')"></a>
    <div class="tgme_widget_message_text js-message_text">
      Квартира 3 комнаты, центр<br>Цена 55000 у.е.
    </div>
  </div>
</div>
<div class="tgme_widget_message_wrap js-widget_message_wrap">
  <div class="tgme_widget_message" data-post="realty/100">
    <div class="tgme_widget_message_text js-message_text">Доброе утро!</div>
  </div>
</div>
"""


def test_parse_feed_extracts_posts():
    posts = tg.parse_feed(_FEED_HTML)
    assert len(posts) == 2
    p0 = posts[0]
    assert p0["id"] == 101
    assert "Квартира 3 комнаты" in p0["text"]
    assert "Цена 55000" in p0["text"]
    assert p0["images"] == ["https://cdn.telegram-cdn.org/file/a.jpg"]
    # Второй пост — без фото.
    assert posts[1]["id"] == 100 and posts[1]["images"] == []


def test_parse_feed_empty():
    assert tg.parse_feed("<html><body>nothing</body></html>") == []


# Пост (102) и ОТВЕТ на него (103) с текстом «Продано». В ответе — цитата
# исходного поста (её НЕ должны принять за текст ответа).
_REPLY_HTML = """
<div class="tgme_widget_message_wrap">
  <div class="tgme_widget_message" data-post="realty/102">
    <div class="tgme_widget_message_text">Дом, 5 соток, 90000 у.е.</div>
  </div>
</div>
<div class="tgme_widget_message_wrap">
  <div class="tgme_widget_message" data-post="realty/103">
    <a class="tgme_widget_message_reply" href="https://t.me/realty/102">
      <div class="tgme_widget_message_text">Дом, 5 соток, 90000 у.е.</div>
    </a>
    <div class="tgme_widget_message_text">Продано ✅</div>
  </div>
</div>
"""


def test_parse_feed_reply_detection():
    posts = {p["id"]: p for p in tg.parse_feed(_REPLY_HTML)}
    # Исходный пост — не ответ.
    assert posts[102]["reply_to"] is None
    # Ответ ссылается на 102, а его собственный текст — только «Продано»
    # (цитата исходного поста вырезана, иначе плодились бы дубли).
    assert posts[103]["reply_to"] == 102
    assert "Продано" in posts[103]["text"]
    assert "90000" not in posts[103]["text"]


def test_inactive_regex():
    R = tg._INACTIVE_RE
    assert R.search("Продано")
    assert R.search("уже продан")
    assert R.search("sotildi")
    assert R.search("снято с продажи")
    assert R.search("неактуально")
    # Активные объявления НЕ должны ловиться.
    assert not R.search("Продажа квартиры")
    assert not R.search("срочно продаю дом")
    assert not R.search("продаётся участок")
