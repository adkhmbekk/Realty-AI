"""
Проверяем бесшовный повтор запроса при обрыве соединения с БД
(см. app/db/retry.py).

Падение БД эмулируем: первый вызов маршрута бросает OperationalError с флагом
connection_invalidated=True (как делает SQLAlchemy при реальном обрыве), второй —
проходит. Заодно убеждаемся, что повтор НЕ срабатывает на обычных ошибках.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.retry import install_db_retry


def _disconnect_error() -> OperationalError:
    """Ошибка-«обрыв соединения», как её помечает SQLAlchemy при разрыве."""
    exc = OperationalError(
        "SELECT 1", {}, Exception("server closed the connection unexpectedly")
    )
    exc.connection_invalidated = True
    return exc


def test_retries_once_on_db_disconnect():
    app = FastAPI()
    calls = {"n": 0}

    @app.post("/echo")
    def echo(payload: dict):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _disconnect_error()
        return {"calls": calls["n"], "got": payload}

    install_db_retry(app)
    client = TestClient(app)

    resp = client.post("/echo", json={"x": 1})

    assert resp.status_code == 200
    # Повтор прошёл, а тело запроса перечиталось из кэша — те же данные.
    assert resp.json() == {"calls": 2, "got": {"x": 1}}


def test_does_not_retry_non_disconnect_errors():
    app = FastAPI()
    calls = {"n": 0}

    @app.get("/boom")
    def boom():
        calls["n"] += 1
        # connection_invalidated по умолчанию False — это НЕ обрыв связи.
        raise OperationalError("SELECT 1", {}, Exception("some logical error"))

    install_db_retry(app)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/boom")

    assert resp.status_code == 500
    assert calls["n"] == 1  # повтора не было
