from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from book_monitor import db, repository
from book_monitor.config import Settings

settings = Settings.from_env()

app = FastAPI(title="Book Price Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_conn():
    conn = db.connect(settings.db_path, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


@app.get("/books")
def get_books(conn=Depends(get_conn)):
    return [
        {"id": book.id, "title": book.title, "isbn13": book.isbn13, "active": book.active}
        for book in repository.list_books(conn)
    ]


@app.get("/stores")
def get_stores(conn=Depends(get_conn)):
    return [
        {"slug": row["slug"], "name": row["name"], "enabled": bool(row["enabled"])}
        for row in repository.list_stores(conn)
    ]


def _require_book(conn, book_id: int):
    book = repository.get_book(conn, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"no book with id {book_id}")
    return book


@app.get("/books/{book_id}/listings")
def get_book_listings(book_id: int, conn=Depends(get_conn)):
    _require_book(conn, book_id)
    return [
        {
            "id": listing.id,
            "store_slug": listing.store_slug,
            "url": listing.url,
            "active": listing.active,
        }
        for listing in repository.list_listings_for_book(conn, book_id)
    ]


@app.get("/books/{book_id}/history")
def get_book_history(
    book_id: int,
    store: str | None = None,
    days: int | None = None,
    conn=Depends(get_conn),
):
    _require_book(conn, book_id)
    # observations_for_book returns raw observation columns only (no
    # store_slug) -- look it up per listing, same approach cli.py's
    # `history` command already uses.
    store_by_listing = {
        listing.id: listing.store_slug
        for listing in repository.list_listings_for_book(conn, book_id)
    }
    rows = repository.observations_for_book(conn, book_id, days=days, store_slug=store)
    return [
        {
            "observed_on": row["observed_on"],
            "store_slug": store_by_listing.get(row["listing_id"]),
            "status": row["status"],
            "price_cents": row["price_cents"],
            "currency": row["currency"],
        }
        for row in rows
    ]
