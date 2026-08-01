from __future__ import annotations

import dataclasses
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from spinewatch import api as api_module
from spinewatch import repository
from spinewatch.api import app, get_conn
from spinewatch.db import init_db
from spinewatch.models import Listing, Observation, ObservationStatus


@pytest.fixture
def conn():
    # check_same_thread=False: this connection is handed to `app` via
    # dependency_overrides below and consumed by a FastAPI sync route
    # running on a different thread (see get_conn in spinewatch/api.py).
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


# --- GET /dashboard ------------------------------------------------------

def test_get_dashboard_includes_latest_observation_per_listing(client, conn):
    repository.upsert_store(conn, "amazon_br", "Amazon Brazil")
    book = repository.add_book(conn, title="Clean Code", isbn13="9780132350884")
    listing = repository.add_listing(
        conn, Listing(id=None, book_id=book.id, store_slug="amazon_br", url="https://amazon.com.br/p/1")
    )
    repository.upsert_observation(
        conn,
        Observation(
            id=None, listing_id=listing.id, observed_on="2026-07-27", observed_at="2026-07-27T03:17:00",
            status=ObservationStatus.OK, price_cents=4000, currency="BRL",
        ),
    )
    repository.upsert_observation(
        conn,
        Observation(
            id=None, listing_id=listing.id, observed_on="2026-07-28", observed_at="2026-07-28T03:17:00",
            status=ObservationStatus.OK, price_cents=4590, currency="BRL",
        ),
    )

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": book.id,
            "title": "Clean Code",
            "isbn13": "9780132350884",
            "active": True,
            "listings": [
                {
                    "id": listing.id,
                    "store_slug": "amazon_br",
                    "url": "https://amazon.com.br/p/1",
                    "active": True,
                    "price_cents": 4590,
                    "currency": "BRL",
                    "status": "ok",
                    "observed_on": "2026-07-28",
                }
            ],
        }
    ]


def test_get_dashboard_listing_with_no_observation_has_null_fields(client, conn):
    repository.upsert_store(conn, "amazon_br", "Amazon Brazil")
    book = repository.add_book(conn, title="Clean Code")
    listing = repository.add_listing(
        conn, Listing(id=None, book_id=book.id, store_slug="amazon_br", url="https://amazon.com.br/p/1")
    )

    response = client.get("/dashboard")

    assert response.json()[0]["listings"] == [
        {
            "id": listing.id,
            "store_slug": "amazon_br",
            "url": "https://amazon.com.br/p/1",
            "active": True,
            "price_cents": None,
            "currency": None,
            "status": None,
            "observed_on": None,
        }
    ]


# --- POST /books ---------------------------------------------------------

def test_create_book_rejects_missing_title_and_isbn(client):
    response = client.post("/books", json={})

    assert response.status_code == 400


def test_create_book_with_valid_isbn10_returns_201_with_isbn13_and_isbn10(client):
    response = client.post("/books", json={"isbn": "0132350882"})

    assert response.status_code == 201
    body = response.json()
    assert body["isbn13"] == "9780132350884"
    assert body["isbn10"] == "0132350882"
    assert body["active"] is True


def test_create_book_rejects_bad_isbn_checksum(client):
    response = client.post("/books", json={"isbn": "0132350889"})

    assert response.status_code == 400


def test_create_book_with_title_only(client):
    response = client.post("/books", json={"title": "Clean Code"})

    assert response.status_code == 201
    assert response.json()["title"] == "Clean Code"


# --- PATCH/DELETE /books/{id} ---------------------------------------------

def test_update_book_active_toggles_flag(client, conn):
    book = repository.add_book(conn, title="Clean Code")

    response = client.patch(f"/books/{book.id}", json={"active": False})

    assert response.status_code == 200
    assert response.json()["active"] is False


def test_update_book_returns_404_for_missing_book(client):
    response = client.patch("/books/999", json={"active": False})

    assert response.status_code == 404


def test_delete_book_returns_204_and_removes_it(client, conn):
    book = repository.add_book(conn, title="Clean Code")

    response = client.delete(f"/books/{book.id}")

    assert response.status_code == 204
    assert repository.get_book(conn, book.id) is None


def test_delete_book_returns_404_for_missing_book(client):
    response = client.delete("/books/999")

    assert response.status_code == 404


# --- PATCH /stores/{slug} --------------------------------------------------

def test_update_store_enabled_toggles_flag(client, conn):
    repository.upsert_store(conn, "amazon_br", "Amazon Brazil")

    response = client.patch("/stores/amazon_br", json={"enabled": False})

    assert response.status_code == 200
    assert response.json() == {"slug": "amazon_br", "name": "Amazon Brazil", "enabled": False}


def test_update_store_returns_404_for_unknown_slug(client):
    response = client.patch("/stores/not_a_real_store", json={"enabled": False})

    assert response.status_code == 404


# --- POST /books/{id}/listings ---------------------------------------------

def test_create_listing_returns_201_with_resolved_store(client, conn):
    repository.upsert_store(conn, "mercado_livre", "Mercado Livre")
    book = repository.add_book(conn, title="Clean Code")

    response = client.post(
        f"/books/{book.id}/listings",
        json={"url": "https://produto.mercadolivre.com.br/MLB-123-foo?utm_source=x"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["store_slug"] == "mercado_livre"
    assert body["url"] == "https://produto.mercadolivre.com.br/MLB-123-foo"
    assert body["active"] is True


def test_create_listing_returns_400_for_url_matching_no_store(client, conn):
    book = repository.add_book(conn, title="Clean Code")

    response = client.post(f"/books/{book.id}/listings", json={"url": "https://www.example.com/dp/1"})

    assert response.status_code == 400


def test_create_listing_returns_404_for_missing_book(client):
    response = client.post(
        "/books/999/listings",
        json={"url": "https://produto.mercadolivre.com.br/MLB-123-foo"},
    )

    assert response.status_code == 404


# --- PATCH /books/{id}/listings/{listing_id} --------------------------------

def test_update_listing_active_toggles_flag(client, conn):
    repository.upsert_store(conn, "amazon_br", "Amazon Brazil")
    book = repository.add_book(conn, title="Clean Code")
    listing = repository.add_listing(
        conn, Listing(id=None, book_id=book.id, store_slug="amazon_br", url="https://amazon.com.br/p/1")
    )

    response = client.patch(f"/books/{book.id}/listings/{listing.id}", json={"active": False})

    assert response.status_code == 200
    assert response.json()["active"] is False


def test_update_listing_returns_404_for_missing_book(client, conn):
    repository.upsert_store(conn, "amazon_br", "Amazon Brazil")
    book = repository.add_book(conn, title="Clean Code")
    listing = repository.add_listing(
        conn, Listing(id=None, book_id=book.id, store_slug="amazon_br", url="https://amazon.com.br/p/1")
    )

    response = client.patch(f"/books/999/listings/{listing.id}", json={"active": False})

    assert response.status_code == 404


def test_update_listing_returns_404_when_listing_does_not_belong_to_book(client, conn):
    repository.upsert_store(conn, "amazon_br", "Amazon Brazil")
    book_a = repository.add_book(conn, title="Clean Code")
    book_b = repository.add_book(conn, title="The Pragmatic Programmer")
    listing = repository.add_listing(
        conn, Listing(id=None, book_id=book_a.id, store_slug="amazon_br", url="https://amazon.com.br/p/1")
    )

    response = client.patch(f"/books/{book_b.id}/listings/{listing.id}", json={"active": False})

    assert response.status_code == 404


# --- API key auth on mutating routes ----------------------------------------

def test_mutating_route_allowed_without_header_when_no_api_key_configured(client):
    # settings.api_key defaults to "" -- unset means auth disabled.
    response = client.post("/books", json={"title": "Clean Code"})

    assert response.status_code == 201


def test_mutating_route_rejects_missing_header_when_api_key_configured(client, monkeypatch):
    monkeypatch.setattr(
        api_module, "settings", dataclasses.replace(api_module.settings, api_key="secret123")
    )

    response = client.post("/books", json={"title": "Clean Code"})

    assert response.status_code == 401


def test_mutating_route_rejects_wrong_header_when_api_key_configured(client, monkeypatch):
    monkeypatch.setattr(
        api_module, "settings", dataclasses.replace(api_module.settings, api_key="secret123")
    )

    response = client.post(
        "/books", json={"title": "Clean Code"}, headers={"X-API-Key": "wrong"}
    )

    assert response.status_code == 401


def test_mutating_route_allows_correct_header_when_api_key_configured(client, monkeypatch):
    monkeypatch.setattr(
        api_module, "settings", dataclasses.replace(api_module.settings, api_key="secret123")
    )

    response = client.post(
        "/books", json={"title": "Clean Code"}, headers={"X-API-Key": "secret123"}
    )

    assert response.status_code == 201


def test_get_routes_unaffected_by_api_key_configuration(client, conn, monkeypatch):
    repository.add_book(conn, title="Clean Code")
    monkeypatch.setattr(
        api_module, "settings", dataclasses.replace(api_module.settings, api_key="secret123")
    )

    response = client.get("/books")

    assert response.status_code == 200
