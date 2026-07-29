from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from book_monitor import repository
from book_monitor.api import app, get_conn
from book_monitor.db import init_db
from book_monitor.models import Listing, Observation, ObservationStatus


@pytest.fixture
def conn():
    # check_same_thread=False: this connection is handed to `app` via
    # dependency_overrides below and consumed by a FastAPI sync route
    # running on a different thread (see get_conn in book_monitor/api.py).
    connection = init_db(":memory:", check_same_thread=False)
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


def test_get_book_listings_returns_404_for_missing_book(client):
    response = client.get("/books/999/listings")

    assert response.status_code == 404


def test_get_book_listings_returns_store_and_url(client, conn):
    repository.upsert_store(conn, "amazon_br", "Amazon Brazil")
    book = repository.add_book(conn, title="Clean Code")
    listing = repository.add_listing(
        conn,
        Listing(id=None, book_id=book.id, store_slug="amazon_br", url="https://amazon.com.br/p/1"),
    )

    response = client.get(f"/books/{book.id}/listings")

    assert response.json() == [
        {"id": listing.id, "store_slug": "amazon_br", "url": "https://amazon.com.br/p/1", "active": True}
    ]


def test_get_book_history_returns_404_for_missing_book(client):
    response = client.get("/books/999/history")

    assert response.status_code == 404


def test_get_book_history_includes_store_slug_and_price(client, conn):
    repository.upsert_store(conn, "amazon_br", "Amazon Brazil")
    book = repository.add_book(conn, title="Clean Code")
    listing = repository.add_listing(
        conn,
        Listing(id=None, book_id=book.id, store_slug="amazon_br", url="https://amazon.com.br/p/1"),
    )
    repository.upsert_observation(
        conn,
        Observation(
            id=None,
            listing_id=listing.id,
            observed_on="2026-07-28",
            observed_at="2026-07-28T03:17:00",
            status=ObservationStatus.OK,
            price_cents=4590,
            currency="BRL",
        ),
    )

    response = client.get(f"/books/{book.id}/history")

    assert response.json() == [
        {
            "observed_on": "2026-07-28",
            "store_slug": "amazon_br",
            "status": "ok",
            "price_cents": 4590,
            "currency": "BRL",
        }
    ]


def test_get_book_history_carries_non_ok_status_without_dropping_row(client, conn):
    repository.upsert_store(conn, "amazon_br", "Amazon Brazil")
    book = repository.add_book(conn, title="Clean Code")
    listing = repository.add_listing(
        conn,
        Listing(id=None, book_id=book.id, store_slug="amazon_br", url="https://amazon.com.br/p/1"),
    )
    repository.upsert_observation(
        conn,
        Observation(
            id=None,
            listing_id=listing.id,
            observed_on="2026-07-28",
            observed_at="2026-07-28T03:17:00",
            status=ObservationStatus.BLOCKED,
            price_cents=None,
            currency=None,
        ),
    )

    response = client.get(f"/books/{book.id}/history")

    assert response.json() == [
        {
            "observed_on": "2026-07-28",
            "store_slug": "amazon_br",
            "status": "blocked",
            "price_cents": None,
            "currency": None,
        }
    ]


def test_get_book_history_filters_by_store(client, conn):
    repository.upsert_store(conn, "amazon_br", "Amazon Brazil")
    repository.upsert_store(conn, "mercado_livre", "Mercado Livre")
    book = repository.add_book(conn, title="Clean Code")
    amazon = repository.add_listing(
        conn, Listing(id=None, book_id=book.id, store_slug="amazon_br", url="https://amazon.com.br/p/1")
    )
    ml = repository.add_listing(
        conn, Listing(id=None, book_id=book.id, store_slug="mercado_livre", url="https://ml.com/p/1")
    )
    repository.upsert_observation(
        conn,
        Observation(
            id=None, listing_id=amazon.id, observed_on="2026-07-28", observed_at="2026-07-28T03:17:00",
            status=ObservationStatus.OK, price_cents=4590, currency="BRL",
        ),
    )
    repository.upsert_observation(
        conn,
        Observation(
            id=None, listing_id=ml.id, observed_on="2026-07-28", observed_at="2026-07-28T03:17:00",
            status=ObservationStatus.OK, price_cents=4200, currency="BRL",
        ),
    )

    response = client.get(f"/books/{book.id}/history", params={"store": "amazon_br"})

    assert [row["store_slug"] for row in response.json()] == ["amazon_br"]


def test_get_book_history_filters_by_days(client, conn):
    repository.upsert_store(conn, "amazon_br", "Amazon Brazil")
    book = repository.add_book(conn, title="Clean Code")
    listing = repository.add_listing(
        conn, Listing(id=None, book_id=book.id, store_slug="amazon_br", url="https://amazon.com.br/p/1")
    )
    old_date = (date.today() - timedelta(days=30)).isoformat()
    recent_date = date.today().isoformat()
    repository.upsert_observation(
        conn,
        Observation(
            id=None, listing_id=listing.id, observed_on=old_date, observed_at=f"{old_date}T03:17:00",
            status=ObservationStatus.OK, price_cents=1000, currency="BRL",
        ),
    )
    repository.upsert_observation(
        conn,
        Observation(
            id=None, listing_id=listing.id, observed_on=recent_date, observed_at=f"{recent_date}T03:17:00",
            status=ObservationStatus.OK, price_cents=2000, currency="BRL",
        ),
    )

    response = client.get(f"/books/{book.id}/history", params={"days": 7})

    assert [row["observed_on"] for row in response.json()] == [recent_date]
