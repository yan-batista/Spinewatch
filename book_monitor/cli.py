from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

import typer
from curl_cffi.requests.exceptions import RequestException

from book_monitor.config import Settings
from book_monitor.db import init_db
from book_monitor import repository, stores
from book_monitor.errors import StoreError
from book_monitor.fetching.http import HttpFetcher
from book_monitor.models import (
    is_valid_isbn10,
    is_valid_isbn13,
    isbn10_to_isbn13,
    normalize_isbn,
)

app = typer.Typer(no_args_is_help=True)
book_app = typer.Typer(no_args_is_help=True)
store_app = typer.Typer(no_args_is_help=True)
fixture_app = typer.Typer(no_args_is_help=True)
app.add_typer(book_app, name="book")
app.add_typer(store_app, name="store")
app.add_typer(fixture_app, name="fixture")


@app.callback()
def main(
    ctx: typer.Context,
    db: str = typer.Option(
        None, "--db", help="Path to the SQLite database file (overrides BOOKMON_DB_PATH)"
    ),
) -> None:
    ctx.obj = db or Settings.from_env().db_path


def _connect(ctx: typer.Context) -> sqlite3.Connection:
    conn = init_db(ctx.obj)
    stores.sync_registry(conn)
    return conn


@app.command("init")
def init_command(ctx: typer.Context) -> None:
    conn = _connect(ctx)
    conn.close()
    typer.echo(f"Initialized database at {ctx.obj}")


def _resolve_isbn(raw: str) -> tuple[str | None, str | None]:
    """Return (isbn13, isbn10) for a raw ISBN-10 or ISBN-13 string, or raise ValueError."""
    normalized = normalize_isbn(raw)
    if len(normalized) == 10:
        if not is_valid_isbn10(normalized):
            raise ValueError(f"invalid ISBN-10 checksum: {raw!r}")
        return isbn10_to_isbn13(normalized), normalized
    if len(normalized) == 13:
        if not is_valid_isbn13(normalized):
            raise ValueError(f"invalid ISBN-13 checksum: {raw!r}")
        return normalized, None
    raise ValueError(
        f"ISBN must be 10 or 13 digits after normalization, got {len(normalized)}: {raw!r}"
    )


@book_app.command("add")
def book_add(
    ctx: typer.Context,
    title: str = typer.Option(None, "--title"),
    alt_title: str = typer.Option(None, "--alt-title"),
    isbn: str = typer.Option(None, "--isbn"),
    author: str = typer.Option(None, "--author"),
) -> None:
    if not title and not isbn:
        typer.echo("Error: at least one of --title or --isbn is required", err=True)
        raise typer.Exit(code=1)

    isbn13 = None
    isbn10 = None
    if isbn:
        try:
            isbn13, isbn10 = _resolve_isbn(isbn)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1)

    conn = _connect(ctx)
    try:
        book = repository.add_book(
            conn, title=title, alt_title=alt_title, isbn13=isbn13, isbn10=isbn10, author=author
        )
    finally:
        conn.close()

    typer.echo(f"Added book {book.id}: {book.title or book.isbn13}")


@book_app.command("list")
def book_list(ctx: typer.Context) -> None:
    conn = _connect(ctx)
    try:
        books = repository.list_books(conn)
        rows = [
            (
                book.id,
                book.title or "",
                book.isbn13 or "",
                "yes" if book.active else "no",
                len(repository.list_listings_for_book(conn, book.id)),
            )
            for book in books
        ]
    finally:
        conn.close()

    if not rows:
        typer.echo("No books.")
        return

    typer.echo(f"{'ID':<4} {'TITLE':<40} {'ISBN-13':<15} {'ACTIVE':<7} {'LISTINGS':<8}")
    for book_id, title, isbn13, active, listing_count in rows:
        typer.echo(f"{book_id:<4} {title:<40} {isbn13:<15} {active:<7} {listing_count:<8}")


def _require_book(conn: sqlite3.Connection, book_id: int):
    book = repository.get_book(conn, book_id)
    if book is None:
        typer.echo(f"Error: no book with id {book_id}", err=True)
        raise typer.Exit(code=1)
    return book


@book_app.command("rm")
def book_rm(
    ctx: typer.Context,
    book_id: int = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt"),
) -> None:
    conn = _connect(ctx)
    try:
        book = _require_book(conn, book_id)
        if not yes:
            label = book.title or book.isbn13
            confirmed = typer.confirm(f"Delete book {book_id} ({label}) and all its history?")
            if not confirmed:
                typer.echo("Aborted.")
                raise typer.Exit(code=1)
        repository.delete_book(conn, book_id)
    finally:
        conn.close()

    typer.echo(f"Deleted book {book_id}.")


@book_app.command("disable")
def book_disable(ctx: typer.Context, book_id: int = typer.Argument(...)) -> None:
    conn = _connect(ctx)
    try:
        _require_book(conn, book_id)
        repository.set_book_active(conn, book_id, False)
    finally:
        conn.close()
    typer.echo(f"Disabled book {book_id}.")


@book_app.command("enable")
def book_enable(ctx: typer.Context, book_id: int = typer.Argument(...)) -> None:
    conn = _connect(ctx)
    try:
        _require_book(conn, book_id)
        repository.set_book_active(conn, book_id, True)
    finally:
        conn.close()
    typer.echo(f"Enabled book {book_id}.")


@store_app.command("list")
def store_list(ctx: typer.Context) -> None:
    conn = _connect(ctx)
    try:
        rows = repository.list_stores(conn)
    finally:
        conn.close()

    # `stores` rows persist even after an adapter file is deleted (sync_registry
    # never deletes, so history/observations stay queryable via ON DELETE
    # RESTRICT). Only show rows for adapters still discoverable on disk.
    on_disk = stores.all_stores()
    rows = [row for row in rows if row["slug"] in on_disk]

    if not rows:
        typer.echo("No stores.")
        return

    typer.echo(f"{'SLUG':<20} {'NAME':<25} {'ENABLED':<7}")
    for row in rows:
        enabled = "yes" if row["enabled"] else "no"
        typer.echo(f"{row['slug']:<20} {row['name']:<25} {enabled:<7}")


def _require_store(conn: sqlite3.Connection, slug: str) -> None:
    if slug not in stores.all_stores():
        typer.echo(f"Error: no store with slug {slug!r}", err=True)
        raise typer.Exit(code=1)


@store_app.command("enable")
def store_enable(ctx: typer.Context, slug: str = typer.Argument(...)) -> None:
    conn = _connect(ctx)
    try:
        _require_store(conn, slug)
        repository.set_store_enabled(conn, slug, True)
    finally:
        conn.close()
    typer.echo(f"Enabled store {slug}.")


@store_app.command("disable")
def store_disable(ctx: typer.Context, slug: str = typer.Argument(...)) -> None:
    conn = _connect(ctx)
    try:
        _require_store(conn, slug)
        repository.set_store_enabled(conn, slug, False)
    finally:
        conn.close()
    typer.echo(f"Disabled store {slug}.")


def _store_slug_for_url(url: str) -> str | None:
    for slug, store_cls in stores.all_stores().items():
        if store_cls().matches_url(url):
            return slug
    return None


@fixture_app.command("save")
def fixture_save(
    url: str = typer.Argument(...),
    name: str = typer.Option(
        None, "--name", help="Output filename (without extension); derived from the URL if omitted"
    ),
) -> None:
    slug = _store_slug_for_url(url)
    if slug is None:
        typer.echo(f"Error: no registered store matches URL {url!r}", err=True)
        raise typer.Exit(code=1)

    fetcher = HttpFetcher(timeout=Settings.from_env().http_timeout)
    try:
        result = fetcher.fetch(url)
    except (StoreError, RequestException) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    finally:
        fetcher.close()

    # Derive a filename from the URL when --name is omitted: the last
    # non-empty path segment (e.g. .../MLB-123-foo -> "MLB-123-foo").
    filename = name or urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1] or "fixture"

    out_dir = Path(Settings.from_env().fixture_dir) / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{filename}.html"
    out_path.write_text(result.html)

    typer.echo(f"Saved fixture to {out_path}")
