import csv
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from book_monitor import repository, stores
from book_monitor.cli import app
from book_monitor.config import Settings
from book_monitor.db import init_db
from book_monitor.errors import BlockedError
from book_monitor.models import (
    FetchResult,
    Listing,
    Observation,
    ObservationStatus,
    ParsedListing,
)

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures"


def _ml_html(price: str = "39.90", currency: str = "BRL", in_stock: bool = True) -> str:
    """Minimal HTML with the JSON-LD Product block the mercado_livre adapter expects."""
    availability = "https://schema.org/InStock" if in_stock else "https://schema.org/OutOfStock"
    payload = json.dumps(
        {
            "@type": "Product",
            "name": "A Book",
            "offers": {"price": price, "priceCurrency": currency, "availability": availability},
        }
    )
    return f'<html><head><script type="application/ld+json">{payload}</script></head></html>'


def test_init_creates_database_file(tmp_path):
    db_path = tmp_path / "books.db"

    result = runner.invoke(app, ["--db", str(db_path), "init"])

    assert result.exit_code == 0
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()
    assert {"books", "stores", "listings", "observations"} <= tables


def test_init_is_safe_to_run_twice(tmp_path):
    db_path = tmp_path / "books.db"

    first = runner.invoke(app, ["--db", str(db_path), "init"])
    second = runner.invoke(app, ["--db", str(db_path), "init"])

    assert first.exit_code == 0
    assert second.exit_code == 0


def test_missing_db_option_uses_bookmon_db_path_env(tmp_path, monkeypatch):
    env_db_path = tmp_path / "from-env.db"
    monkeypatch.setenv("BOOKMON_DB_PATH", str(env_db_path))

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert env_db_path.exists()


def test_db_option_overrides_environment(tmp_path, monkeypatch):
    env_db_path = tmp_path / "from-env.db"
    explicit_db_path = tmp_path / "explicit.db"
    monkeypatch.setenv("BOOKMON_DB_PATH", str(env_db_path))

    result = runner.invoke(app, ["--db", str(explicit_db_path), "init"])

    assert result.exit_code == 0
    assert explicit_db_path.exists()
    assert not env_db_path.exists()


def test_add_book_with_hyphenated_isbn10_stores_isbn13(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    result = runner.invoke(
        app, ["--db", str(db_path), "book", "add", "--title", "SICP", "--isbn", "0-306-40615-2"]
    )

    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT isbn13, isbn10 FROM books WHERE title = 'SICP'").fetchone()
    conn.close()
    assert row == ("9780306406157", "0306406152")


def test_add_book_with_isbn13_directly(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    result = runner.invoke(
        app,
        ["--db", str(db_path), "book", "add", "--title", "Clean Code", "--isbn", "978-0-13-235088-4"],
    )

    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT isbn13, isbn10 FROM books WHERE title = 'Clean Code'").fetchone()
    conn.close()
    assert row == ("9780132350884", None)


def test_add_rejects_missing_title_and_isbn(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    result = runner.invoke(app, ["--db", str(db_path), "book", "add", "--author", "Nobody"])

    assert result.exit_code == 1
    assert "title" in result.output.lower()
    assert "isbn" in result.output.lower()


def test_add_rejects_bad_isbn_checksum_with_explanatory_message(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    result = runner.invoke(
        app, ["--db", str(db_path), "book", "add", "--title", "Bad ISBN Book", "--isbn", "0306406153"]
    )

    assert result.exit_code == 1
    assert "checksum" in result.output.lower()


def test_add_with_title_only_and_no_isbn(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    result = runner.invoke(app, ["--db", str(db_path), "book", "add", "--title", "No ISBN Book"])

    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT title, isbn13 FROM books WHERE title = 'No ISBN Book'").fetchone()
    conn.close()
    assert row == ("No ISBN Book", None)


def test_list_shows_added_books_with_isbn_and_active_state(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])
    runner.invoke(app, ["--db", str(db_path), "book", "add", "--title", "SICP", "--isbn", "0306406152"])

    result = runner.invoke(app, ["--db", str(db_path), "book", "list"])

    assert result.exit_code == 0
    assert "SICP" in result.output
    assert "9780306406157" in result.output
    assert "yes" in result.output


def test_list_shows_no_books_message_when_catalog_empty(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    result = runner.invoke(app, ["--db", str(db_path), "book", "list"])

    assert result.exit_code == 0
    assert "no books" in result.output.lower()


def test_list_shows_zero_listings_for_a_book_with_no_links(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])
    runner.invoke(app, ["--db", str(db_path), "book", "add", "--title", "Unlinked Book"])

    result = runner.invoke(app, ["--db", str(db_path), "book", "list"])

    lines = [line for line in result.output.splitlines() if "Unlinked Book" in line]
    assert len(lines) == 1
    assert lines[0].split()[-1] == "0"


def test_disable_then_book_shows_inactive_in_list(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])
    runner.invoke(app, ["--db", str(db_path), "book", "add", "--title", "Disable Me"])

    disable_result = runner.invoke(app, ["--db", str(db_path), "book", "disable", "1"])
    list_result = runner.invoke(app, ["--db", str(db_path), "book", "list"])

    assert disable_result.exit_code == 0
    line = next(l for l in list_result.output.splitlines() if "Disable Me" in l)
    assert " no " in f" {line} "


def test_enable_reactivates_a_disabled_book(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])
    runner.invoke(app, ["--db", str(db_path), "book", "add", "--title", "Toggle Me"])
    runner.invoke(app, ["--db", str(db_path), "book", "disable", "1"])

    enable_result = runner.invoke(app, ["--db", str(db_path), "book", "enable", "1"])
    list_result = runner.invoke(app, ["--db", str(db_path), "book", "list"])

    assert enable_result.exit_code == 0
    line = next(l for l in list_result.output.splitlines() if "Toggle Me" in l)
    assert " yes " in f" {line} "


def test_disable_unknown_book_id_errors(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    result = runner.invoke(app, ["--db", str(db_path), "book", "disable", "999"])

    assert result.exit_code == 1
    assert "no book with id 999" in result.output.lower()


def test_rm_with_yes_flag_deletes_without_prompting(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])
    runner.invoke(app, ["--db", str(db_path), "book", "add", "--title", "Delete Me"])

    result = runner.invoke(app, ["--db", str(db_path), "book", "rm", "1", "--yes"])

    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT count(*) FROM books WHERE id = 1").fetchone()[0]
    conn.close()
    assert count == 0


def test_rm_without_yes_prompts_and_aborts_on_no(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])
    runner.invoke(app, ["--db", str(db_path), "book", "add", "--title", "Keep Me"])

    result = runner.invoke(app, ["--db", str(db_path), "book", "rm", "1"], input="n\n")

    assert result.exit_code == 1
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT count(*) FROM books WHERE id = 1").fetchone()[0]
    conn.close()
    assert count == 1


def test_rm_without_yes_confirms_and_deletes_on_yes(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])
    runner.invoke(app, ["--db", str(db_path), "book", "add", "--title", "Confirm Delete"])

    result = runner.invoke(app, ["--db", str(db_path), "book", "rm", "1"], input="y\n")

    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT count(*) FROM books WHERE id = 1").fetchone()[0]
    conn.close()
    assert count == 0


def test_rm_unknown_book_id_errors(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    result = runner.invoke(app, ["--db", str(db_path), "book", "rm", "999", "--yes"])

    assert result.exit_code == 1
    assert "no book with id 999" in result.output.lower()


# --- store list/enable/disable ------------------------------------------

def test_store_list_shows_mercado_livre_enabled_on_first_run(tmp_path):
    db_path = tmp_path / "books.db"

    result = runner.invoke(app, ["--db", str(db_path), "store", "list"])

    assert result.exit_code == 0
    line = next(l for l in result.output.splitlines() if "mercado_livre" in l)
    assert " yes " in f" {line} "


def test_store_disable_then_enable_round_trip(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "store", "list"])

    disable_result = runner.invoke(app, ["--db", str(db_path), "store", "disable", "mercado_livre"])
    disabled_list = runner.invoke(app, ["--db", str(db_path), "store", "list"])

    assert disable_result.exit_code == 0
    line = next(l for l in disabled_list.output.splitlines() if "mercado_livre" in l)
    assert " no " in f" {line} "

    enable_result = runner.invoke(app, ["--db", str(db_path), "store", "enable", "mercado_livre"])
    enabled_list = runner.invoke(app, ["--db", str(db_path), "store", "list"])

    assert enable_result.exit_code == 0
    line = next(l for l in enabled_list.output.splitlines() if "mercado_livre" in l)
    assert " yes " in f" {line} "


def test_store_disable_unknown_slug_errors(tmp_path):
    db_path = tmp_path / "books.db"

    result = runner.invoke(app, ["--db", str(db_path), "store", "disable", "unknown_slug"])

    assert result.exit_code == 1
    assert "unknown_slug" in result.output.lower()


def test_store_enable_errors_for_slug_whose_adapter_is_no_longer_on_disk(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    # First run with the real registry: syncs mercado_livre into the stores table.
    runner.invoke(app, ["--db", str(db_path), "store", "list"])

    # Simulate the adapter file having been deleted: all_stores() no longer
    # reports it, so _require_store should treat the slug as unknown even
    # though a row for it still exists in the DB.
    monkeypatch.setattr("book_monitor.stores.all_stores", lambda: {})

    result = runner.invoke(app, ["--db", str(db_path), "store", "enable", "mercado_livre"])

    assert result.exit_code == 1
    assert "mercado_livre" in result.output.lower()


def test_store_list_hides_a_row_whose_adapter_is_no_longer_on_disk(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    # First run with the real registry: syncs mercado_livre into the stores table.
    runner.invoke(app, ["--db", str(db_path), "store", "list"])

    # Simulate the adapter file having been deleted: all_stores() no longer
    # reports it, but sync_registry (called by _connect on every command)
    # never deletes existing rows, so the DB row for it must survive.
    monkeypatch.setattr("book_monitor.stores.all_stores", lambda: {})

    result = runner.invoke(app, ["--db", str(db_path), "store", "list"])

    assert result.exit_code == 0
    assert "mercado_livre" not in result.output

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT slug FROM stores WHERE slug = 'mercado_livre'").fetchone()
    conn.close()
    assert row is not None


# --- fixture save --------------------------------------------------------

def test_fixture_save_writes_html_under_matched_store_slug(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKMON_FIXTURE_DIR", str(tmp_path))
    monkeypatch.setattr(
        "book_monitor.cli.HttpFetcher.fetch",
        lambda self, url: FetchResult(
            html="<html>fixture</html>", status_code=200, final_url=url, fetcher="http"
        ),
    )

    result = runner.invoke(
        app,
        ["fixture", "save", "https://produto.mercadolivre.com.br/MLB-123-foo", "--name", "manual"],
    )

    assert result.exit_code == 0
    saved = tmp_path / "mercado_livre" / "manual.html"
    assert saved.exists()
    assert saved.read_text() == "<html>fixture</html>"


def test_fixture_save_derives_name_from_url_when_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKMON_FIXTURE_DIR", str(tmp_path))
    monkeypatch.setattr(
        "book_monitor.cli.HttpFetcher.fetch",
        lambda self, url: FetchResult(
            html="<html>fixture</html>", status_code=200, final_url=url, fetcher="http"
        ),
    )

    result = runner.invoke(
        app, ["fixture", "save", "https://produto.mercadolivre.com.br/MLB-123-foo"]
    )

    assert result.exit_code == 0
    saved = tmp_path / "mercado_livre" / "MLB-123-foo.html"
    assert saved.exists()


def test_fixture_save_errors_for_url_matching_no_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKMON_FIXTURE_DIR", str(tmp_path))

    result = runner.invoke(app, ["fixture", "save", "https://www.example.com/dp/123"])

    assert result.exit_code == 1
    assert "no registered store" in result.output.lower()


# --- crawl ---------------------------------------------------------------

def test_crawl_successful_listing_prints_ok_summary_and_exits_zero(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Book")
    repository.add_listing(
        conn,
        Listing(
            id=None,
            book_id=book.id,
            store_slug="mercado_livre",
            url="https://produto.mercadolivre.com.br/MLB-1",
        ),
    )
    conn.close()

    monkeypatch.setattr(
        "book_monitor.cli.HttpFetcher.fetch",
        lambda self, url: FetchResult(html=_ml_html(), status_code=200, final_url=url, fetcher="http"),
    )

    result = runner.invoke(app, ["--db", str(db_path), "crawl"])

    assert result.exit_code == 0
    assert "ok" in result.output
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM observations WHERE status = 'ok'").fetchone()[0]
    conn.close()
    assert count == 1


def test_crawl_exits_nonzero_when_every_listing_fails(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Book")
    repository.add_listing(
        conn,
        Listing(
            id=None,
            book_id=book.id,
            store_slug="mercado_livre",
            url="https://produto.mercadolivre.com.br/MLB-1",
        ),
    )
    conn.close()

    def _raise(self, url):
        raise BlockedError("blocked")

    monkeypatch.setattr("book_monitor.cli.HttpFetcher.fetch", _raise)

    # --max-escalations 0: this test is about the exit-code/status-mapping
    # contract for a fully-blocked crawl, not escalation -- without this the
    # default budget (25) would have the CLI spin up a real BrowserFetcher.
    result = runner.invoke(app, ["--db", str(db_path), "crawl", "--max-escalations", "0"])

    assert result.exit_code == 1
    conn = sqlite3.connect(db_path)
    status = conn.execute("SELECT status FROM observations").fetchone()[0]
    conn.close()
    assert status == "blocked"


def test_crawl_dry_run_writes_no_observations(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Book")
    repository.add_listing(
        conn,
        Listing(
            id=None,
            book_id=book.id,
            store_slug="mercado_livre",
            url="https://produto.mercadolivre.com.br/MLB-1",
        ),
    )
    conn.close()

    monkeypatch.setattr(
        "book_monitor.cli.HttpFetcher.fetch",
        lambda self, url: FetchResult(html=_ml_html(), status_code=200, final_url=url, fetcher="http"),
    )

    result = runner.invoke(app, ["--db", str(db_path), "crawl", "--dry-run"])

    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    conn.close()
    assert count == 0


def test_crawl_book_option_restricts_to_the_matching_listing(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book_a = repository.add_book(conn, title="Book A")
    book_b = repository.add_book(conn, title="Book B")
    listing_a = repository.add_listing(
        conn,
        Listing(
            id=None,
            book_id=book_a.id,
            store_slug="mercado_livre",
            url="https://produto.mercadolivre.com.br/MLB-1",
        ),
    )
    listing_b = repository.add_listing(
        conn,
        Listing(
            id=None,
            book_id=book_b.id,
            store_slug="mercado_livre",
            url="https://produto.mercadolivre.com.br/MLB-2",
        ),
    )
    conn.close()

    monkeypatch.setattr(
        "book_monitor.cli.HttpFetcher.fetch",
        lambda self, url: FetchResult(html=_ml_html(), status_code=200, final_url=url, fetcher="http"),
    )

    result = runner.invoke(app, ["--db", str(db_path), "crawl", "--book", str(book_b.id)])

    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    listing_ids = {row["listing_id"] for row in conn.execute("SELECT listing_id FROM observations")}
    conn.close()
    assert listing_ids == {listing_b.id}
    assert listing_a.id not in listing_ids


def test_crawl_only_store_restricts_to_the_matching_listing(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    repository.upsert_store(conn, "other_store", "Other Store")
    book_a = repository.add_book(conn, title="Book A")
    book_b = repository.add_book(conn, title="Book B")
    listing_a = repository.add_listing(
        conn,
        Listing(
            id=None,
            book_id=book_a.id,
            store_slug="mercado_livre",
            url="https://produto.mercadolivre.com.br/MLB-1",
        ),
    )
    listing_b = repository.add_listing(
        conn,
        Listing(id=None, book_id=book_b.id, store_slug="other_store", url="https://other.example/2"),
    )
    conn.close()

    class _OtherStore:
        name = "Other Store"
        request_delay = (0.0, 0.0)

        def parse_listing(self, html, url):
            return ParsedListing(price_cents=999, currency="BRL", in_stock=True, raw_price_text="9.99")

    other_store = _OtherStore()
    original_get_store = stores.get_store
    original_all_stores = stores.all_stores()
    monkeypatch.setattr(
        stores,
        "get_store",
        lambda slug: other_store if slug == "other_store" else original_get_store(slug),
    )
    monkeypatch.setattr(
        stores,
        "all_stores",
        lambda: {**original_all_stores, "other_store": _OtherStore},
    )
    monkeypatch.setattr(
        "book_monitor.cli.HttpFetcher.fetch",
        lambda self, url: FetchResult(html=_ml_html(), status_code=200, final_url=url, fetcher="http"),
    )

    result = runner.invoke(app, ["--db", str(db_path), "crawl", "--only-store", "other_store"])

    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    listing_ids = {row["listing_id"] for row in conn.execute("SELECT listing_id FROM observations")}
    conn.close()
    assert listing_ids == {listing_b.id}
    assert listing_a.id not in listing_ids


def test_crawl_force_recrawls_a_listing_already_observed_today(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Book")
    listing = repository.add_listing(
        conn,
        Listing(
            id=None,
            book_id=book.id,
            store_slug="mercado_livre",
            url="https://produto.mercadolivre.com.br/MLB-1",
        ),
    )
    repository.upsert_observation(
        conn,
        Observation(
            id=None,
            listing_id=listing.id,
            observed_on=date.today().isoformat(),
            observed_at=datetime.now().isoformat(),
            status=ObservationStatus.BLOCKED,
            error="previously blocked",
        ),
    )
    conn.close()

    monkeypatch.setattr(
        "book_monitor.cli.HttpFetcher.fetch",
        lambda self, url: FetchResult(
            html=_ml_html(price="59.90"), status_code=200, final_url=url, fetcher="http"
        ),
    )

    without_force = runner.invoke(app, ["--db", str(db_path), "crawl"])
    assert without_force.exit_code == 0  # nothing due today is not a failure

    with_force = runner.invoke(app, ["--db", str(db_path), "crawl", "--force"])
    assert with_force.exit_code == 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status, price_cents FROM observations WHERE listing_id = ?", (listing.id,)
    ).fetchone()
    conn.close()
    assert row["status"] == "ok"
    assert row["price_cents"] == 5990


def test_crawl_only_store_with_unknown_slug_errors_instead_of_silently_doing_nothing(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    result = runner.invoke(app, ["--db", str(db_path), "crawl", "--only-store", "nonexistent_slug"])

    assert result.exit_code == 1
    assert "no store with slug" in result.output.lower()


def test_crawl_book_option_with_nonexistent_id_errors_instead_of_silently_doing_nothing(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    result = runner.invoke(app, ["--db", str(db_path), "crawl", "--book", "99999"])

    assert result.exit_code == 1
    assert "no book with id" in result.output.lower()


# --- --max-escalations -----------------------------------------------------

def test_crawl_max_escalations_flag_overrides_default_and_is_passed_through(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    captured = {}

    def _fake_run_crawl(conn, fetcher, **kwargs):
        captured.update(kwargs)
        from book_monitor.crawl import CrawlSummary

        return CrawlSummary(status_counts={}, listings_attempted=0, duration_seconds=0.0)

    monkeypatch.setattr("book_monitor.cli.run_crawl", _fake_run_crawl)

    result = runner.invoke(app, ["--db", str(db_path), "crawl", "--max-escalations", "3"])

    assert result.exit_code == 0
    assert captured["max_escalations"] == 3


def test_crawl_summary_line_reports_escalations_used(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    def _fake_run_crawl(conn, fetcher, **kwargs):
        from book_monitor.crawl import CrawlSummary

        return CrawlSummary(
            status_counts={"ok": 1},
            listings_attempted=1,
            duration_seconds=0.0,
            escalations_used=2,
        )

    monkeypatch.setattr("book_monitor.cli.run_crawl", _fake_run_crawl)

    result = runner.invoke(app, ["--db", str(db_path), "crawl"])

    assert result.exit_code == 0
    assert "escalations=2" in result.output


def test_crawl_omitting_max_escalations_flag_uses_settings_default(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    captured = {}

    def _fake_run_crawl(conn, fetcher, **kwargs):
        captured.update(kwargs)
        from book_monitor.crawl import CrawlSummary

        return CrawlSummary(status_counts={}, listings_attempted=0, duration_seconds=0.0)

    monkeypatch.setattr("book_monitor.cli.run_crawl", _fake_run_crawl)

    result = runner.invoke(app, ["--db", str(db_path), "crawl"])

    assert result.exit_code == 0
    assert captured["max_escalations"] == Settings().max_escalations


def test_crawl_closes_fetcher_even_when_run_crawl_raises_unexpectedly(tmp_path, monkeypatch):
    # run_crawl's per-listing containment catches every exception (see
    # crawl.py's `except Exception` catch-all), so there is no reachable path
    # where a *listing* failure escapes run_crawl itself -- per the brief,
    # noting this rather than forcing a contrived listing-level case. This
    # test instead verifies the CLI's try/finally by making run_crawl itself
    # raise (e.g. as a stand-in for a bug/crash outside the per-listing
    # pipeline, such as in selection or summary construction).
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    closed = []
    monkeypatch.setattr("book_monitor.cli.HttpFetcher.close", lambda self: closed.append(True))

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("book_monitor.cli.run_crawl", _raise)

    result = runner.invoke(app, ["--db", str(db_path), "crawl"])

    assert result.exit_code != 0
    assert closed == [True]


# --- search / link / links / unlink ---------------------------------------

_ML_SEARCH_RESULTS_HTML = (FIXTURES / "mercado_livre" / "search_results.html").read_text()


def test_search_prints_candidates_and_confirming_creates_listing(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Codigo Limpo")
    conn.close()

    monkeypatch.setattr(
        "book_monitor.cli.HttpFetcher.fetch",
        lambda self, url: FetchResult(
            html=_ML_SEARCH_RESULTS_HTML, status_code=200, final_url=url, fetcher="http"
        ),
    )

    result = runner.invoke(
        app, ["--db", str(db_path), "search", str(book.id), "--store", "mercado_livre"], input="1\n"
    )

    assert result.exit_code == 0
    assert "1." in result.output
    assert "2." in result.output

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT store_slug, url, store_product_id, store_title, active FROM listings"
    ).fetchone()
    conn.close()
    assert row["store_slug"] == "mercado_livre"
    assert row["url"] == (
        "https://produto.mercadolivre.com.br/MLB-3776391953-livro-codigo-limpo-"
        "robert-c-martin-habilidades-praticas-do-agile-software-_JM"
    )
    assert row["store_product_id"] == "3776391953"
    assert row["store_title"] == "Livro Código Limpo | Robert C. Martin | Clean Code"
    assert row["active"] == 1


def test_search_with_no_matching_results_reports_message_and_exits_zero(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Nothing Matches This")
    conn.close()

    monkeypatch.setattr(
        "book_monitor.cli.HttpFetcher.fetch",
        lambda self, url: FetchResult(
            html="<html><body>no results</body></html>", status_code=200, final_url=url, fetcher="http"
        ),
    )

    result = runner.invoke(app, ["--db", str(db_path), "search", str(book.id), "--store", "mercado_livre"])

    assert result.exit_code == 0
    assert "no candidates" in result.output.lower()


def test_search_reports_search_not_supported_for_store_without_search(tmp_path, monkeypatch):
    from book_monitor.stores.base import Store

    class _NoSearchStore(Store):
        slug = "no_search"
        name = "No Search Store"

        def parse_listing(self, html, url):
            raise NotImplementedError

        def matches_url(self, url):
            return False

        def normalize_url(self, url):
            return url

    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Book")
    conn.close()

    no_search_store = _NoSearchStore()
    original_all_stores = stores.all_stores()
    original_get_store = stores.get_store
    monkeypatch.setattr(
        stores, "all_stores", lambda: {**original_all_stores, "no_search": _NoSearchStore}
    )
    monkeypatch.setattr(
        stores,
        "get_store",
        lambda slug: no_search_store if slug == "no_search" else original_get_store(slug),
    )

    result = runner.invoke(app, ["--db", str(db_path), "search", str(book.id), "--store", "no_search"])

    assert result.exit_code == 1
    assert "does not support search" in result.output.lower()


def test_search_reports_network_failure_cleanly_instead_of_crashing(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Book")
    conn.close()

    def _raise(self, url):
        raise BlockedError("blocked by store")

    monkeypatch.setattr("book_monitor.cli.HttpFetcher.fetch", _raise)

    result = runner.invoke(app, ["--db", str(db_path), "search", str(book.id), "--store", "mercado_livre"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "error: blocked by store" in result.output.lower()


def test_link_creates_listing_with_no_fetch_performed(tmp_path, monkeypatch):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Book")
    conn.close()

    fetch_calls = []
    monkeypatch.setattr(
        "book_monitor.cli.HttpFetcher.fetch",
        lambda self, url: fetch_calls.append(url),
    )

    result = runner.invoke(
        app,
        [
            "--db", str(db_path), "link", str(book.id),
            "https://produto.mercadolivre.com.br/MLB-123-foo?utm_source=x",
        ],
    )

    assert result.exit_code == 0
    assert fetch_calls == []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT store_slug, url, store_title, store_product_id, active FROM listings"
    ).fetchone()
    conn.close()
    assert row["store_slug"] == "mercado_livre"
    assert row["url"] == "https://produto.mercadolivre.com.br/MLB-123-foo"
    assert row["store_title"] is None
    assert row["store_product_id"] is None
    assert row["active"] == 1


def test_link_url_matching_no_store_errors(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Book")
    conn.close()

    result = runner.invoke(
        app, ["--db", str(db_path), "link", str(book.id), "https://www.example.com/dp/1"]
    )

    assert result.exit_code == 1
    assert "no registered store" in result.output.lower()


def test_link_to_existing_inactive_listing_reactivates_it(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Book")
    listing = repository.add_listing(
        conn,
        Listing(
            id=None,
            book_id=book.id,
            store_slug="mercado_livre",
            url="https://produto.mercadolivre.com.br/MLB-123-foo",
        ),
    )
    repository.set_listing_active(conn, listing.id, False)
    conn.close()

    result = runner.invoke(
        app,
        ["--db", str(db_path), "link", str(book.id), "https://produto.mercadolivre.com.br/MLB-123-foo"],
    )

    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, active FROM listings").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["id"] == listing.id
    assert rows[0]["active"] == 1


def test_link_to_existing_inactive_listing_preserves_metadata_earned_by_search(tmp_path):
    # A listing previously populated with real title/product-id via a
    # `search` confirm, then unlinked, must not have that metadata blanked
    # back to NULL by a later plain `link` reactivation -- `link` has no
    # new data to offer, so it must not destroy data `search` already earned.
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Book")
    listing = repository.add_listing(
        conn,
        Listing(
            id=None,
            book_id=book.id,
            store_slug="mercado_livre",
            url="https://produto.mercadolivre.com.br/MLB-123-foo",
            store_product_id="123",
            store_title="Real Title From Search",
        ),
    )
    repository.set_listing_active(conn, listing.id, False)
    conn.close()

    result = runner.invoke(
        app,
        ["--db", str(db_path), "link", str(book.id), "https://produto.mercadolivre.com.br/MLB-123-foo"],
    )

    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, active, store_title, store_product_id FROM listings"
    ).fetchone()
    conn.close()
    assert row["id"] == listing.id
    assert row["active"] == 1
    assert row["store_title"] == "Real Title From Search"
    assert row["store_product_id"] == "123"


def test_search_confirm_reactivating_a_linked_listing_refreshes_stale_metadata(tmp_path, monkeypatch):
    # A listing created via plain `link` never fetches, so store_title/
    # store_product_id start out NULL. After `unlink` + a later `search`
    # confirm for the same product, the reactivated row should pick up the
    # real title/product-id instead of staying permanently NULL.
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    matched_url = (
        "https://produto.mercadolivre.com.br/MLB-3776391953-livro-codigo-limpo-"
        "robert-c-martin-habilidades-praticas-do-agile-software-_JM"
    )

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Codigo Limpo")
    listing = repository.add_listing(
        conn,
        Listing(id=None, book_id=book.id, store_slug="mercado_livre", url=matched_url),
    )
    conn.close()

    runner.invoke(app, ["--db", str(db_path), "unlink", str(listing.id)])

    monkeypatch.setattr(
        "book_monitor.cli.HttpFetcher.fetch",
        lambda self, url: FetchResult(
            html=_ML_SEARCH_RESULTS_HTML, status_code=200, final_url=url, fetcher="http"
        ),
    )

    result = runner.invoke(
        app, ["--db", str(db_path), "search", str(book.id), "--store", "mercado_livre"], input="1\n"
    )

    assert result.exit_code == 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, url, store_title, store_product_id, active FROM listings").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["id"] == listing.id
    assert rows[0]["url"] == matched_url
    assert rows[0]["store_title"] == "Livro Código Limpo | Robert C. Martin | Clean Code"
    assert rows[0]["store_product_id"] == "3776391953"
    assert rows[0]["active"] == 1


def test_links_shows_active_and_inactive_listings_with_state(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Book")
    repository.add_listing(
        conn,
        Listing(
            id=None, book_id=book.id, store_slug="mercado_livre",
            url="https://produto.mercadolivre.com.br/MLB-1",
        ),
    )
    inactive_listing = repository.add_listing(
        conn,
        Listing(
            id=None, book_id=book.id, store_slug="mercado_livre",
            url="https://produto.mercadolivre.com.br/MLB-2",
        ),
    )
    repository.set_listing_active(conn, inactive_listing.id, False)
    conn.close()

    result = runner.invoke(app, ["--db", str(db_path), "links", str(book.id)])

    assert result.exit_code == 0
    active_line = next(l for l in result.output.splitlines() if "MLB-1" in l)
    inactive_line = next(l for l in result.output.splitlines() if "MLB-2" in l)
    assert " yes " in f" {active_line} "
    assert " no " in f" {inactive_line} "


def test_unlink_deactivates_listing_and_excludes_it_from_crawl_selection(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Book")
    listing = repository.add_listing(
        conn,
        Listing(
            id=None, book_id=book.id, store_slug="mercado_livre",
            url="https://produto.mercadolivre.com.br/MLB-1",
        ),
    )
    conn.close()

    result = runner.invoke(app, ["--db", str(db_path), "unlink", str(listing.id)])
    assert result.exit_code == 0

    links_result = runner.invoke(app, ["--db", str(db_path), "links", str(book.id)])
    line = next(l for l in links_result.output.splitlines() if "MLB-1" in l)
    assert " no " in f" {line} "

    conn = init_db(db_path)
    due = repository.listings_due_today(conn)
    active = repository.active_listings(conn)
    conn.close()
    assert due == []
    assert active == []


def test_unlink_unknown_listing_id_errors(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    result = runner.invoke(app, ["--db", str(db_path), "unlink", "999"])

    assert result.exit_code == 1
    assert "no listing with id 999" in result.output.lower()


# --- history --------------------------------------------------------------

def test_history_shows_ok_and_failure_rows_in_descending_date_order(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book = repository.add_book(conn, title="Book")
    listing = repository.add_listing(
        conn, Listing(id=None, book_id=book.id, store_slug="mercado_livre", url="https://x/1")
    )
    repository.upsert_observation(
        conn,
        Observation(
            id=None, listing_id=listing.id, observed_on="2026-07-20",
            observed_at="2026-07-20T00:00:00", status=ObservationStatus.OK,
            price_cents=9490, currency="BRL",
        ),
    )
    repository.upsert_observation(
        conn,
        Observation(
            id=None, listing_id=listing.id, observed_on="2026-07-25",
            observed_at="2026-07-25T00:00:00", status=ObservationStatus.BLOCKED,
        ),
    )
    conn.close()

    result = runner.invoke(app, ["--db", str(db_path), "history", str(book.id)])

    assert result.exit_code == 0
    lines = result.output.splitlines()
    ok_line = next(l for l in lines if "2026-07-20" in l)
    blocked_line = next(l for l in lines if "2026-07-25" in l)
    assert lines.index(blocked_line) < lines.index(ok_line)  # descending date order
    assert "94.90" in ok_line
    assert "blocked" in blocked_line
    # the failure row must not show a blank or zero-looking price cell
    assert "0.00" not in blocked_line


def test_history_days_and_store_filters_compose(tmp_path):
    # history_command never passes an explicit `today=` to
    # observations_for_book, so its --days cutoff is computed from the real
    # date.today() at test-run time -- observation dates here must be
    # relative to that (like tests/test_crawl.py's pattern), not fixed
    # calendar strings, or this test would start failing on its own once the
    # calendar moves past whatever window hardcoded dates were calibrated for.
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    today = date.today()
    outside_window = (today - timedelta(days=20)).isoformat()  # older than --days 10
    inside_window_a = (today - timedelta(days=8)).isoformat()
    inside_window_b = today.isoformat()

    conn = init_db(db_path)
    repository.upsert_store(conn, "amazon_br", "Amazon Brazil")
    book = repository.add_book(conn, title="Book")
    ml_listing = repository.add_listing(
        conn, Listing(id=None, book_id=book.id, store_slug="mercado_livre", url="https://x/ml")
    )
    az_listing = repository.add_listing(
        conn, Listing(id=None, book_id=book.id, store_slug="amazon_br", url="https://x/az")
    )
    for day in (outside_window, inside_window_a, inside_window_b):
        repository.upsert_observation(
            conn,
            Observation(
                id=None, listing_id=ml_listing.id, observed_on=day,
                observed_at=f"{day}T00:00:00", status=ObservationStatus.OK,
                price_cents=1000, currency="BRL",
            ),
        )
        repository.upsert_observation(
            conn,
            Observation(
                id=None, listing_id=az_listing.id, observed_on=day,
                observed_at=f"{day}T00:00:00", status=ObservationStatus.OK,
                price_cents=2000, currency="BRL",
            ),
        )
    conn.close()

    result = runner.invoke(
        app,
        ["--db", str(db_path), "history", str(book.id), "--days", "10", "--store", "amazon_br"],
    )

    assert result.exit_code == 0
    lines = [
        l for l in result.output.splitlines()
        if l.startswith(("20",))  # date-leading rows only, skip the header
    ]
    dates_shown = {l.split()[0] for l in lines}
    assert dates_shown == {inside_window_a, inside_window_b}
    assert "mercado_livre" not in result.output


def test_history_unknown_book_id_errors(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    result = runner.invoke(app, ["--db", str(db_path), "history", "999"])

    assert result.exit_code == 1
    assert "no book with id 999" in result.output.lower()


# --- export ---------------------------------------------------------------

def test_export_writes_csv_with_expected_header_and_row_count(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book_a = repository.add_book(conn, title="Book A", isbn13="9780132350884")
    book_b = repository.add_book(conn, title="Book B")
    listing_a = repository.add_listing(
        conn, Listing(id=None, book_id=book_a.id, store_slug="mercado_livre", url="https://x/a")
    )
    listing_b = repository.add_listing(
        conn, Listing(id=None, book_id=book_b.id, store_slug="mercado_livre", url="https://x/b")
    )
    repository.upsert_observation(
        conn,
        Observation(
            id=None, listing_id=listing_a.id, observed_on="2026-07-20",
            observed_at="2026-07-20T00:00:00", status=ObservationStatus.OK,
            price_cents=1000, currency="BRL",
        ),
    )
    repository.upsert_observation(
        conn,
        Observation(
            id=None, listing_id=listing_b.id, observed_on="2026-07-21",
            observed_at="2026-07-21T00:00:00", status=ObservationStatus.OK,
            price_cents=2000, currency="BRL",
        ),
    )
    conn.close()

    csv_path = tmp_path / "export.csv"
    result = runner.invoke(app, ["--db", str(db_path), "export", "--csv", str(csv_path)])

    assert result.exit_code == 0
    assert csv_path.exists()
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == [
            "book_title", "isbn13", "store_slug", "observed_on", "status",
            "price_cents", "currency",
        ]
        rows = list(reader)
    assert len(rows) == 2


def test_export_book_filter_restricts_to_one_book(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book_a = repository.add_book(conn, title="Book A")
    book_b = repository.add_book(conn, title="Book B")
    listing_a = repository.add_listing(
        conn, Listing(id=None, book_id=book_a.id, store_slug="mercado_livre", url="https://x/a")
    )
    listing_b = repository.add_listing(
        conn, Listing(id=None, book_id=book_b.id, store_slug="mercado_livre", url="https://x/b")
    )
    for listing in (listing_a, listing_b):
        repository.upsert_observation(
            conn,
            Observation(
                id=None, listing_id=listing.id, observed_on="2026-07-20",
                observed_at="2026-07-20T00:00:00", status=ObservationStatus.OK,
                price_cents=1000, currency="BRL",
            ),
        )
    conn.close()

    csv_path = tmp_path / "export.csv"
    result = runner.invoke(
        app, ["--db", str(db_path), "export", "--csv", str(csv_path), "--book", str(book_a.id)]
    )

    assert result.exit_code == 0
    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["book_title"] == "Book A"


def test_export_since_and_book_filters_compose(tmp_path):
    db_path = tmp_path / "books.db"
    runner.invoke(app, ["--db", str(db_path), "init"])

    conn = init_db(db_path)
    book_a = repository.add_book(conn, title="Book A")
    book_b = repository.add_book(conn, title="Book B")
    listing_a = repository.add_listing(
        conn, Listing(id=None, book_id=book_a.id, store_slug="mercado_livre", url="https://x/a")
    )
    listing_b = repository.add_listing(
        conn, Listing(id=None, book_id=book_b.id, store_slug="mercado_livre", url="https://x/b")
    )
    for listing in (listing_a, listing_b):
        for day in ("2026-07-10", "2026-07-25"):
            repository.upsert_observation(
                conn,
                Observation(
                    id=None, listing_id=listing.id, observed_on=day,
                    observed_at=f"{day}T00:00:00", status=ObservationStatus.OK,
                    price_cents=1000, currency="BRL",
                ),
            )
    conn.close()

    csv_path = tmp_path / "export.csv"
    result = runner.invoke(
        app,
        [
            "--db", str(db_path), "export", "--csv", str(csv_path),
            "--book", str(book_a.id), "--since", "2026-07-20",
        ],
    )

    assert result.exit_code == 0
    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["book_title"] == "Book A"
    assert rows[0]["observed_on"] == "2026-07-25"
