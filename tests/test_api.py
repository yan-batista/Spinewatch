from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from book_monitor import repository
from book_monitor.api import app, get_conn
from book_monitor.db import init_db


@pytest.fixture
def conn():
    connection = init_db(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def client(conn):
    def _override():
        yield conn

    app.dependency_overrides[get_conn] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_cors_middleware_is_registered():
    middleware_classes = {m.cls.__name__ for m in app.user_middleware}
    assert "CORSMiddleware" in middleware_classes


def test_get_books_returns_all_books(client, conn):
    repository.add_book(conn, title="Clean Code", isbn13="9780132350884")
    repository.add_book(conn, title="The Pragmatic Programmer")

    response = client.get("/books")

    assert response.status_code == 200
    titles = {book["title"] for book in response.json()}
    assert titles == {"Clean Code", "The Pragmatic Programmer"}


def test_get_books_includes_isbn_and_active_flag(client, conn):
    book = repository.add_book(conn, title="Clean Code", isbn13="9780132350884")
    repository.set_book_active(conn, book.id, False)

    response = client.get("/books")

    assert response.json() == [
        {"id": book.id, "title": "Clean Code", "isbn13": "9780132350884", "active": False}
    ]


def test_get_stores_returns_slug_name_enabled(client, conn):
    repository.upsert_store(conn, "amazon_br", "Amazon Brazil")
    repository.upsert_store(conn, "mercado_livre", "Mercado Livre", enabled=False)

    response = client.get("/stores")

    assert response.json() == [
        {"slug": "amazon_br", "name": "Amazon Brazil", "enabled": True},
        {"slug": "mercado_livre", "name": "Mercado Livre", "enabled": False},
    ]
