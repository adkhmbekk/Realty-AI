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
