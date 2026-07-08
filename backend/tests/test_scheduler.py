"""
Подписка ОТКЛЮЧЕНА (переход на тарифы, 2026-07): фоновые функции подписки —
стабы, возвращающие 0 и ничего не рассылающие. Тест фиксирует это поведение
(полноценные проверки вернутся вместе с платными тарифами).
"""
from app.services import scheduler


def test_subscription_warnings_disabled(db):
    assert scheduler.run_subscription_warnings(db) == 0


def test_expire_due_subscriptions_disabled(db):
    assert scheduler.expire_due_subscriptions(db) == 0
