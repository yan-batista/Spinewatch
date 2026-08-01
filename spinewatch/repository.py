from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from spinewatch.models import Book, Listing, Observation


# --- books -------------------------------------------------------------

def _row_to_book(row: sqlite3.Row) -> Book:
    return Book(
        id=row["id"],
        title=row["title"],
        alt_title=row["alt_title"],
        isbn13=row["isbn13"],
        isbn10=row["isbn10"],
        author=row["author"],
        active=bool(row["active"]),
        created_at=row["created_at"],
    )


def add_book(
    conn: sqlite3.Connection,
    *,
    title: str | None = None,
    alt_title: str | None = None,
    isbn13: str | None = None,
    isbn10: str | None = None,
    author: str | None = None,
) -> Book:
    cur = conn.execute(
        "INSERT INTO books (title, alt_title, isbn13, isbn10, author) "
        "VALUES (?, ?, ?, ?, ?)",
        (title, alt_title, isbn13, isbn10, author),
    )
    conn.commit()
    return get_book(conn, cur.lastrowid)


def get_book(conn: sqlite3.Connection, book_id: int) -> Book | None:
    row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    return _row_to_book(row) if row is not None else None


def list_books(conn: sqlite3.Connection, *, active_only: bool = False) -> list[Book]:
    query = "SELECT * FROM books"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY id"
    return [_row_to_book(row) for row in conn.execute(query).fetchall()]


def set_book_active(conn: sqlite3.Connection, book_id: int, active: bool) -> None:
    conn.execute("UPDATE books SET active = ? WHERE id = ?", (int(active), book_id))
    conn.commit()


def delete_book(conn: sqlite3.Connection, book_id: int) -> None:
    conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    conn.commit()


# --- stores --------------------------------------------------------------

def upsert_store(
    conn: sqlite3.Connection, slug: str, name: str, *, enabled: bool = True
) -> None:
    conn.execute(
        "INSERT INTO stores (slug, name, enabled) VALUES (?, ?, ?) "
        "ON CONFLICT (slug) DO UPDATE SET name = excluded.name, enabled = excluded.enabled",
        (slug, name, int(enabled)),
    )
    conn.commit()


def list_stores(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM stores ORDER BY slug").fetchall()


def set_store_enabled(conn: sqlite3.Connection, slug: str, enabled: bool) -> None:
    conn.execute("UPDATE stores SET enabled = ? WHERE slug = ?", (int(enabled), slug))
    conn.commit()


# --- listings --------------------------------------------------------------

def _row_to_listing(row: sqlite3.Row) -> Listing:
    return Listing(
        id=row["id"],
        book_id=row["book_id"],
        store_slug=row["store_slug"],
        url=row["url"],
        store_product_id=row["store_product_id"],
        store_title=row["store_title"],
        active=bool(row["active"]),
        created_at=row["created_at"],
    )


def add_listing(conn: sqlite3.Connection, listing: Listing) -> Listing:
    cur = conn.execute(
        "INSERT INTO listings (book_id, store_slug, url, store_product_id, store_title, active) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            listing.book_id,
            listing.store_slug,
            listing.url,
            listing.store_product_id,
            listing.store_title,
            int(listing.active),
        ),
    )
    conn.commit()
    return get_listing(conn, cur.lastrowid)


def get_listing(conn: sqlite3.Connection, listing_id: int) -> Listing | None:
    row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    return _row_to_listing(row) if row is not None else None


def list_listings_for_book(conn: sqlite3.Connection, book_id: int) -> list[Listing]:
    rows = conn.execute(
        "SELECT * FROM listings WHERE book_id = ? ORDER BY id", (book_id,)
    ).fetchall()
    return [_row_to_listing(row) for row in rows]


def delete_listing(conn: sqlite3.Connection, listing_id: int) -> None:
    conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
    conn.commit()


def find_listing(
    conn: sqlite3.Connection, book_id: int, store_slug: str, url: str
) -> Listing | None:
    """Look up a listing by its `UNIQUE (book_id, store_slug, url)` key.

    Caller normalizes `url` first via `store.normalize_url`.
    """
    row = conn.execute(
        "SELECT * FROM listings WHERE book_id = ? AND store_slug = ? AND url = ?",
        (book_id, store_slug, url),
    ).fetchone()
    return _row_to_listing(row) if row is not None else None


def set_listing_active(conn: sqlite3.Connection, listing_id: int, active: bool) -> None:
    conn.execute("UPDATE listings SET active = ? WHERE id = ?", (int(active), listing_id))
    conn.commit()


def link_listing(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    store_slug: str,
    url: str,
    store_product_id: str | None = None,
    store_title: str | None = None,
) -> tuple[Listing, bool]:
    """Shared write path for `books search`'s confirm step, `books link`, and
    the API's `POST /books/{id}/listings`: reactivate a matching inactive
    listing (decision 2 in the phase 6 plan -- `unlink` soft-deletes, so
    relinking the same URL must not hit the `UNIQUE (book_id, store_slug,
    url)` constraint), or insert a new one.

    Returns (listing, created) where created=False means the listing already
    existed (whether it was already active or got reactivated here).
    Caller is responsible for normalizing `url` first via `store.normalize_url`.
    """
    existing = find_listing(conn, book_id, store_slug, url)
    if existing is not None:
        if not existing.active:
            set_listing_active(conn, existing.id, True)
            update_listing_metadata(
                conn, existing.id, store_title=store_title, store_product_id=store_product_id
            )
            existing = get_listing(conn, existing.id)
        return existing, False

    listing = add_listing(
        conn,
        Listing(
            id=None,
            book_id=book_id,
            store_slug=store_slug,
            url=url,
            store_product_id=store_product_id,
            store_title=store_title,
        ),
    )
    return listing, True


def update_listing_metadata(
    conn: sqlite3.Connection,
    listing_id: int,
    *,
    store_title: str | None,
    store_product_id: str | None,
) -> None:
    """Set store_title/store_product_id, but never blank an existing value
    with None -- a None here means "caller has nothing new to offer" (e.g.
    plain `books link`, which never fetches), not "clear this field".
    """
    conn.execute(
        "UPDATE listings SET "
        "store_title = COALESCE(?, store_title), "
        "store_product_id = COALESCE(?, store_product_id) "
        "WHERE id = ?",
        (store_title, store_product_id, listing_id),
    )
    conn.commit()


# --- observations ------------------------------------------------------

def upsert_observation(conn: sqlite3.Connection, observation: Observation) -> None:
    conn.execute(
        """
        INSERT INTO observations
            (listing_id, observed_on, observed_at, status, price_cents,
             currency, in_stock, seller, fetcher, raw_price_text, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (listing_id, observed_on) DO UPDATE SET
            observed_at    = excluded.observed_at,
            status         = excluded.status,
            price_cents    = excluded.price_cents,
            currency       = excluded.currency,
            in_stock       = excluded.in_stock,
            seller         = excluded.seller,
            fetcher        = excluded.fetcher,
            raw_price_text = excluded.raw_price_text,
            error          = excluded.error
        """,
        (
            observation.listing_id,
            observation.observed_on,
            observation.observed_at,
            observation.status,
            observation.price_cents,
            observation.currency,
            None if observation.in_stock is None else int(observation.in_stock),
            observation.seller,
            observation.fetcher,
            observation.raw_price_text,
            observation.error,
        ),
    )
    conn.commit()


def observations_for_book(
    conn: sqlite3.Connection,
    book_id: int,
    *,
    days: int | None = None,
    store_slug: str | None = None,
    today: str | None = None,
) -> list[sqlite3.Row]:
    query = """
        SELECT o.* FROM observations o
        JOIN listings l ON l.id = o.listing_id
        WHERE l.book_id = ?
    """
    params: list = [book_id]
    if store_slug is not None:
        query += " AND l.store_slug = ?"
        params.append(store_slug)
    if days is not None:
        reference = date.fromisoformat(today) if today else date.today()
        cutoff = (reference - timedelta(days=days)).isoformat()
        query += " AND o.observed_on >= ?"
        params.append(cutoff)
    query += " ORDER BY o.observed_on DESC"
    return conn.execute(query, params).fetchall()


def export_observations(
    conn: sqlite3.Connection,
    *,
    book_id: int | None = None,
    since: str | None = None,
) -> list[sqlite3.Row]:
    """Flat, cross-book export for `books export --csv` (FR-23).

    A fresh query rather than a reuse of `observations_for_book` (which is
    scoped to one book): export spans the whole catalog by design.
    """
    query = """
        SELECT b.title AS book_title, b.isbn13 AS isbn13, l.store_slug AS store_slug,
               o.observed_on AS observed_on, o.status AS status,
               o.price_cents AS price_cents, o.currency AS currency
        FROM observations o
        JOIN listings l ON l.id = o.listing_id
        JOIN books b ON b.id = l.book_id
        WHERE 1 = 1
    """
    params: list = []
    if book_id is not None:
        query += " AND l.book_id = ?"
        params.append(book_id)
    if since is not None:
        query += " AND o.observed_on >= ?"
        params.append(since)
    query += " ORDER BY l.book_id, o.observed_on, l.store_slug"
    return conn.execute(query, params).fetchall()


def latest_observations_by_listing(conn: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    """The most recent observation (by observed_on) per listing_id, across
    the whole catalog -- backs `GET /dashboard`'s per-listing current price
    without an N+1 query per listing.
    """
    rows = conn.execute(
        """
        SELECT o.* FROM observations o
        JOIN (
            SELECT listing_id, MAX(observed_on) AS observed_on
            FROM observations GROUP BY listing_id
        ) latest ON latest.listing_id = o.listing_id AND latest.observed_on = o.observed_on
        """
    ).fetchall()
    return {row["listing_id"]: row for row in rows}


def listings_due_today(
    conn: sqlite3.Connection,
    *,
    only_store: str | None = None,
    only_book: int | None = None,
    today: str | None = None,
) -> list[Listing]:
    today = today or date.today().isoformat()
    query = """
        SELECT l.* FROM listings l
        JOIN books b ON b.id = l.book_id
        JOIN stores s ON s.slug = l.store_slug
        WHERE l.active = 1 AND b.active = 1 AND s.enabled = 1
          AND NOT EXISTS (
              SELECT 1 FROM observations o
              WHERE o.listing_id = l.id AND o.observed_on = ?
          )
    """
    params: list = [today]
    if only_store is not None:
        query += " AND l.store_slug = ?"
        params.append(only_store)
    if only_book is not None:
        query += " AND l.book_id = ?"
        params.append(only_book)
    query += " ORDER BY l.id"
    rows = conn.execute(query, params).fetchall()
    return [_row_to_listing(row) for row in rows]


def active_listings(
    conn: sqlite3.Connection,
    *,
    only_store: str | None = None,
    only_book: int | None = None,
) -> list[Listing]:
    query = """
        SELECT l.* FROM listings l
        JOIN books b ON b.id = l.book_id
        JOIN stores s ON s.slug = l.store_slug
        WHERE l.active = 1 AND b.active = 1 AND s.enabled = 1
    """
    params: list = []
    if only_store is not None:
        query += " AND l.store_slug = ?"
        params.append(only_store)
    if only_book is not None:
        query += " AND l.book_id = ?"
        params.append(only_book)
    query += " ORDER BY l.id"
    rows = conn.execute(query, params).fetchall()
    return [_row_to_listing(row) for row in rows]
