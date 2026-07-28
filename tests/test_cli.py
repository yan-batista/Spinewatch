import sqlite3

from typer.testing import CliRunner

from book_monitor.cli import app
from book_monitor.models import FetchResult

runner = CliRunner()


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

    result = runner.invoke(app, ["fixture", "save", "https://www.amazon.com.br/dp/123"])

    assert result.exit_code == 1
    assert "no registered store" in result.output.lower()
