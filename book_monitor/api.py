from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from book_monitor import db, repository, stores
from book_monitor.config import Settings
from book_monitor.models import resolve_isbn

settings = Settings.from_env()

app = FastAPI(title="Book Price Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


def get_conn():
    conn = db.connect(settings.db_path, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Applied only to mutating (POST/PATCH/DELETE) routes. `settings.api_key`
    empty (the default/unset posture) disables auth entirely, matching
    today's public-read behavior; non-empty requires an exact match.
    """
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


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


def _book_dict(book) -> dict:
    return {
        "id": book.id,
        "title": book.title,
        "isbn13": book.isbn13,
        "isbn10": book.isbn10,
        "alt_title": book.alt_title,
        "author": book.author,
        "active": book.active,
    }


def _listing_dict(listing) -> dict:
    return {
        "id": listing.id,
        "store_slug": listing.store_slug,
        "url": listing.url,
        "active": listing.active,
    }


class BookCreate(BaseModel):
    title: str | None = None
    alt_title: str | None = None
    isbn: str | None = None
    author: str | None = None


class ActiveUpdate(BaseModel):
    active: bool


class StoreUpdate(BaseModel):
    enabled: bool


class ListingCreate(BaseModel):
    url: str


@app.get("/dashboard")
def get_dashboard(conn=Depends(get_conn)):
    latest_by_listing = repository.latest_observations_by_listing(conn)
    result = []
    for book in repository.list_books(conn):
        listings = []
        for listing in repository.list_listings_for_book(conn, book.id):
            obs = latest_by_listing.get(listing.id)
            listings.append(
                {
                    "id": listing.id,
                    "store_slug": listing.store_slug,
                    "url": listing.url,
                    "active": listing.active,
                    "price_cents": obs["price_cents"] if obs is not None else None,
                    "currency": obs["currency"] if obs is not None else None,
                    "status": obs["status"] if obs is not None else None,
                    "observed_on": obs["observed_on"] if obs is not None else None,
                }
            )
        result.append(
            {
                "id": book.id,
                "title": book.title,
                "isbn13": book.isbn13,
                "active": book.active,
                "listings": listings,
            }
        )
    return result


@app.post("/books", status_code=201, dependencies=[Depends(require_api_key)])
def create_book(payload: BookCreate, conn=Depends(get_conn)):
    if not payload.title and not payload.isbn:
        raise HTTPException(status_code=400, detail="at least one of title or isbn is required")

    isbn13 = None
    isbn10 = None
    if payload.isbn:
        try:
            isbn13, isbn10 = resolve_isbn(payload.isbn)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    book = repository.add_book(
        conn,
        title=payload.title,
        alt_title=payload.alt_title,
        isbn13=isbn13,
        isbn10=isbn10,
        author=payload.author,
    )
    return _book_dict(book)


@app.patch("/books/{book_id}", dependencies=[Depends(require_api_key)])
def update_book(book_id: int, payload: ActiveUpdate, conn=Depends(get_conn)):
    _require_book(conn, book_id)
    repository.set_book_active(conn, book_id, payload.active)
    return _book_dict(repository.get_book(conn, book_id))


@app.delete("/books/{book_id}", status_code=204, dependencies=[Depends(require_api_key)])
def remove_book(book_id: int, conn=Depends(get_conn)):
    _require_book(conn, book_id)
    repository.delete_book(conn, book_id)


@app.patch("/stores/{slug}", dependencies=[Depends(require_api_key)])
def update_store(slug: str, payload: StoreUpdate, conn=Depends(get_conn)):
    if slug not in stores.all_stores():
        raise HTTPException(status_code=404, detail=f"no store with slug {slug!r}")
    repository.set_store_enabled(conn, slug, payload.enabled)
    row = next(row for row in repository.list_stores(conn) if row["slug"] == slug)
    return {"slug": row["slug"], "name": row["name"], "enabled": bool(row["enabled"])}


@app.post(
    "/books/{book_id}/listings", status_code=201, dependencies=[Depends(require_api_key)]
)
def create_listing(book_id: int, payload: ListingCreate, conn=Depends(get_conn)):
    _require_book(conn, book_id)
    store = stores.store_for_url(payload.url)
    if store is None:
        raise HTTPException(
            status_code=400, detail=f"no registered store matches URL {payload.url!r}"
        )
    normalized = store.normalize_url(payload.url)
    listing, _created = repository.link_listing(
        conn, book_id=book_id, store_slug=store.slug, url=normalized
    )
    return _listing_dict(listing)


@app.patch(
    "/books/{book_id}/listings/{listing_id}", dependencies=[Depends(require_api_key)]
)
def update_listing(
    book_id: int, listing_id: int, payload: ActiveUpdate, conn=Depends(get_conn)
):
    _require_book(conn, book_id)
    listing = repository.get_listing(conn, listing_id)
    if listing is None or listing.book_id != book_id:
        raise HTTPException(status_code=404, detail=f"no listing with id {listing_id}")
    repository.set_listing_active(conn, listing_id, payload.active)
    return _listing_dict(repository.get_listing(conn, listing_id))


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
