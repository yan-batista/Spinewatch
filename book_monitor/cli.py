from __future__ import annotations

import sqlite3

import typer

from book_monitor.config import Settings
from book_monitor.db import init_db
from book_monitor import repository
from book_monitor.models import (
    is_valid_isbn10,
    is_valid_isbn13,
    isbn10_to_isbn13,
    normalize_isbn,
)

app = typer.Typer(no_args_is_help=True)
book_app = typer.Typer(no_args_is_help=True)
app.add_typer(book_app, name="book")


@app.callback()
def main(
    ctx: typer.Context,
    db: str = typer.Option(
        None, "--db", help="Path to the SQLite database file (overrides BOOKMON_DB_PATH)"
    ),
) -> None:
    ctx.obj = db or Settings.from_env().db_path


def _connect(ctx: typer.Context) -> sqlite3.Connection:
    return init_db(ctx.obj)


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
