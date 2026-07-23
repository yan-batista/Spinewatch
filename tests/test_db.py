import sqlite3

import pytest

from book_monitor.db import MIGRATIONS, connect, init_db, migrate


def test_connect_enables_foreign_keys(tmp_path):
    conn = connect(tmp_path / "books.db")
    try:
        (fk_on,) = conn.execute("PRAGMA foreign_keys").fetchone()
        assert fk_on == 1
    finally:
        conn.close()


def test_connect_enables_wal_journal_mode(tmp_path):
    conn = connect(tmp_path / "books.db")
    try:
        (mode,) = conn.execute("PRAGMA journal_mode").fetchone()
        assert mode.lower() == "wal"
    finally:
        conn.close()


def test_init_db_creates_all_four_tables(tmp_path):
    conn = init_db(tmp_path / "books.db")
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        table_names = {row["name"] for row in rows}
        assert {"books", "stores", "listings", "observations"} <= table_names
    finally:
        conn.close()


def test_init_db_sets_user_version_to_latest_migration(tmp_path):
    conn = init_db(tmp_path / "books.db")
    try:
        (version,) = conn.execute("PRAGMA user_version").fetchone()
        assert version == len(MIGRATIONS)
    finally:
        conn.close()


def test_init_db_is_safe_to_run_twice(tmp_path):
    db_path = tmp_path / "books.db"
    init_db(db_path).close()
    conn = init_db(db_path)  # must not raise on an already-migrated database
    try:
        (version,) = conn.execute("PRAGMA user_version").fetchone()
        assert version == len(MIGRATIONS)
    finally:
        conn.close()


def test_migrate_is_idempotent_on_an_existing_connection(tmp_path):
    conn = connect(tmp_path / "books.db")
    try:
        migrate(conn)
        migrate(conn)  # second call applies nothing, must not raise
        (version,) = conn.execute("PRAGMA user_version").fetchone()
        assert version == len(MIGRATIONS)
    finally:
        conn.close()


def test_books_table_rejects_row_with_no_title_and_no_isbn(tmp_path):
    conn = init_db(tmp_path / "books.db")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO books (title, isbn13) VALUES (NULL, NULL)")
            conn.commit()
    finally:
        conn.close()


def test_deleting_a_book_cascades_to_listings_and_observations(tmp_path):
    conn = init_db(tmp_path / "books.db")
    try:
        conn.execute("INSERT INTO stores (slug, name) VALUES ('ml', 'Mercado Livre')")
        cur = conn.execute("INSERT INTO books (title, isbn13) VALUES ('A Book', NULL)")
        book_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO listings (book_id, store_slug, url) VALUES (?, 'ml', 'https://x')",
            (book_id,),
        )
        listing_id = cur.lastrowid
        conn.execute(
            "INSERT INTO observations "
            "(listing_id, observed_on, observed_at, status, price_cents) "
            "VALUES (?, '2026-07-23', '2026-07-23T00:00:00', 'ok', 1999)",
            (listing_id,),
        )
        conn.commit()

        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.commit()

        remaining_listings = conn.execute(
            "SELECT count(*) FROM listings WHERE book_id = ?", (book_id,)
        ).fetchone()[0]
        remaining_observations = conn.execute(
            "SELECT count(*) FROM observations WHERE listing_id = ?", (listing_id,)
        ).fetchone()[0]
        assert remaining_listings == 0
        assert remaining_observations == 0
    finally:
        conn.close()


def test_observations_check_rejects_ok_status_without_price(tmp_path):
    conn = init_db(tmp_path / "books.db")
    try:
        conn.execute("INSERT INTO stores (slug, name) VALUES ('ml', 'Mercado Livre')")
        cur = conn.execute("INSERT INTO books (title, isbn13) VALUES ('A Book', NULL)")
        book_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO listings (book_id, store_slug, url) VALUES (?, 'ml', 'https://x')",
            (book_id,),
        )
        listing_id = cur.lastrowid
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO observations "
                "(listing_id, observed_on, observed_at, status, price_cents) "
                "VALUES (?, '2026-07-23', '2026-07-23T00:00:00', 'ok', NULL)",
                (listing_id,),
            )
            conn.commit()
    finally:
        conn.close()
