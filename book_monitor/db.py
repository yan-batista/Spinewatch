from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

_SCHEMA_V1 = """
CREATE TABLE books (
    id          INTEGER PRIMARY KEY,
    title       TEXT,
    alt_title   TEXT,
    isbn13      TEXT,
    isbn10      TEXT,
    author      TEXT,
    active      INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (title IS NOT NULL OR isbn13 IS NOT NULL)
);

CREATE UNIQUE INDEX idx_books_isbn13
    ON books (isbn13) WHERE isbn13 IS NOT NULL;

CREATE TABLE stores (
    slug        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE listings (
    id                INTEGER PRIMARY KEY,
    book_id           INTEGER NOT NULL REFERENCES books (id) ON DELETE CASCADE,
    store_slug        TEXT    NOT NULL REFERENCES stores (slug) ON DELETE RESTRICT,
    url               TEXT    NOT NULL,
    store_product_id  TEXT,
    store_title       TEXT,
    active            INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (book_id, store_slug, url)
);

CREATE INDEX idx_listings_book         ON listings (book_id);
CREATE INDEX idx_listings_store_active ON listings (store_slug, active);

CREATE TABLE observations (
    id              INTEGER PRIMARY KEY,
    listing_id      INTEGER NOT NULL REFERENCES listings (id) ON DELETE CASCADE,
    observed_on     TEXT    NOT NULL,
    observed_at     TEXT    NOT NULL,
    status          TEXT    NOT NULL CHECK (status IN
                        ('ok', 'unavailable', 'blocked', 'not_found', 'parse_error', 'error')),
    price_cents     INTEGER CHECK (price_cents IS NULL OR price_cents >= 0),
    currency        TEXT,
    in_stock        INTEGER CHECK (in_stock IN (0, 1)),
    seller          TEXT,
    fetcher         TEXT,
    raw_price_text  TEXT,
    error           TEXT,
    UNIQUE (listing_id, observed_on),
    CHECK ((status = 'ok') = (price_cents IS NOT NULL))
);

CREATE INDEX idx_obs_listing_date ON observations (listing_id, observed_on);
CREATE INDEX idx_obs_date         ON observations (observed_on);
"""


def _migration_1_initial_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_V1)


MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [
    _migration_1_initial_schema,
]


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    (current,) = conn.execute("PRAGMA user_version").fetchone()
    for version, migration in enumerate(MIGRATIONS, start=1):
        if version <= current:
            continue
        try:
            migration(conn)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def init_db(db_path: str | Path) -> sqlite3.Connection:
    conn = connect(db_path)
    migrate(conn)
    return conn
