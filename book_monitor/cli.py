from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

import typer
from curl_cffi.requests.exceptions import RequestException

from book_monitor.config import Settings
from book_monitor.crawl import run_crawl
from book_monitor.db import init_db
from book_monitor import repository, stores
from book_monitor.errors import StoreError
from book_monitor.fetching.http import HttpFetcher
from book_monitor.models import resolve_isbn
from book_monitor.search import find_candidates

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


@app.command("crawl")
def crawl_command(
    ctx: typer.Context,
    only_store: str = typer.Option(
        None, "--only-store", help="Restrict the crawl to one store slug"
    ),
    book: int = typer.Option(None, "--book", help="Restrict the crawl to one book id"),
    force: bool = typer.Option(
        False, "--force", help="Re-crawl listings already observed today"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Run fetch/parse but write no observations"
    ),
    max_escalations: int = typer.Option(
        None,
        "--max-escalations",
        help="Maximum browser-fallback escalations this run (overrides BOOKMON_MAX_ESCALATIONS)",
    ),
) -> None:
    settings = Settings.from_env()
    conn = _connect(ctx)
    fetcher = HttpFetcher(timeout=settings.http_timeout)
    try:
        if only_store is not None:
            _require_store(conn, only_store)
        if book is not None:
            _require_book(conn, book)
        summary = run_crawl(
            conn,
            fetcher,
            only_store=only_store,
            only_book=book,
            force=force,
            dry_run=dry_run,
            max_escalations=max_escalations if max_escalations is not None else settings.max_escalations,
            browser_timeout=settings.browser_timeout,
        )
    finally:
        fetcher.close()
        conn.close()

    counts = " ".join(f"{status}={count}" for status, count in summary.status_counts.items())
    typer.echo(
        f"Crawl finished: {counts or 'nothing to do'} "
        f"({summary.listings_attempted} attempted, {summary.duration_seconds:.2f}s, "
        f"escalations={summary.escalations_used})"
    )
    if not summary.succeeded:
        raise typer.Exit(code=1)


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
            isbn13, isbn10 = resolve_isbn(isbn)
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


@fixture_app.command("save")
def fixture_save(
    url: str = typer.Argument(...),
    name: str = typer.Option(
        None, "--name", help="Output filename (without extension); derived from the URL if omitted"
    ),
) -> None:
    store = stores.store_for_url(url)
    if store is None:
        typer.echo(f"Error: no registered store matches URL {url!r}", err=True)
        raise typer.Exit(code=1)
    slug = store.slug

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


def _format_price(price_cents: int | None, currency: str | None) -> str:
    if price_cents is None:
        return "price unknown"
    return f"{currency or ''} {price_cents / 100:.2f}".strip()


def _link_or_reactivate(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    store_slug: str,
    url: str,
    store_product_id: str | None,
    store_title: str | None,
) -> None:
    """CLI print wrapper around `repository.link_listing` -- distinguishes
    "already active" from "reactivated" from "newly linked" in the echoed
    message, on top of the (listing, created) tuple the repository returns.
    """
    was_active = False
    existing = repository.find_listing(conn, book_id, store_slug, url)
    if existing is not None and existing.active:
        was_active = True

    listing, created = repository.link_listing(
        conn,
        book_id=book_id,
        store_slug=store_slug,
        url=url,
        store_product_id=store_product_id,
        store_title=store_title,
    )
    if created:
        typer.echo(f"Linked listing {listing.id}: {url}")
    elif was_active:
        typer.echo(f"Listing {listing.id} is already linked and active.")
    else:
        typer.echo(f"Reactivated listing {listing.id}: {url}")


@app.command("search")
def search_command(
    ctx: typer.Context,
    book_id: int = typer.Argument(...),
    store_slug: str = typer.Option(
        ..., "--store", help="Store slug to search (required; searching every store isn't supported)"
    ),
) -> None:
    conn = _connect(ctx)
    try:
        book = _require_book(conn, book_id)
        _require_store(conn, store_slug)
        store = stores.get_store(store_slug)

        fetcher = HttpFetcher(timeout=Settings.from_env().http_timeout)
        try:
            candidates, query_used = find_candidates(fetcher, store, book)
        except (StoreError, RequestException) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1)
        finally:
            fetcher.close()

        if not candidates:
            typer.echo("No candidates found.")
            return

        typer.echo(f"Candidates for query {query_used!r}:")
        for i, candidate in enumerate(candidates, start=1):
            price = _format_price(candidate.price_cents, candidate.currency)
            typer.echo(f"{i}. {candidate.store_title} ({price}) - {candidate.url}")

        selection = typer.prompt("Select a candidate to link (0 to cancel)", type=int)
        if selection == 0:
            typer.echo("Cancelled.")
            return
        if selection < 1 or selection > len(candidates):
            typer.echo(f"Error: invalid selection {selection}", err=True)
            raise typer.Exit(code=1)

        chosen = candidates[selection - 1]
        url = store.normalize_url(chosen.url)
        _link_or_reactivate(
            conn,
            book_id=book.id,
            store_slug=store_slug,
            url=url,
            store_product_id=chosen.store_product_id,
            store_title=chosen.store_title,
        )
    finally:
        conn.close()


@app.command("link")
def link_command(
    ctx: typer.Context,
    book_id: int = typer.Argument(...),
    url: str = typer.Argument(...),
) -> None:
    conn = _connect(ctx)
    try:
        book = _require_book(conn, book_id)
        store = stores.store_for_url(url)
        if store is None:
            typer.echo(f"Error: no registered store matches URL {url!r}", err=True)
            raise typer.Exit(code=1)

        normalized = store.normalize_url(url)
        _link_or_reactivate(
            conn,
            book_id=book.id,
            store_slug=store.slug,
            url=normalized,
            store_product_id=None,
            store_title=None,
        )
    finally:
        conn.close()


@app.command("links")
def links_command(ctx: typer.Context, book_id: int = typer.Argument(...)) -> None:
    conn = _connect(ctx)
    try:
        _require_book(conn, book_id)
        listings = repository.list_listings_for_book(conn, book_id)
    finally:
        conn.close()

    if not listings:
        typer.echo("No listings.")
        return

    typer.echo(f"{'ID':<4} {'STORE':<15} {'ACTIVE':<7} {'TITLE':<30} URL")
    for listing in listings:
        active = "yes" if listing.active else "no"
        typer.echo(
            f"{listing.id:<4} {listing.store_slug:<15} {active:<7} "
            f"{(listing.store_title or ''):<30} {listing.url}"
        )


@app.command("unlink")
def unlink_command(ctx: typer.Context, listing_id: int = typer.Argument(...)) -> None:
    conn = _connect(ctx)
    try:
        listing = repository.get_listing(conn, listing_id)
        if listing is None:
            typer.echo(f"Error: no listing with id {listing_id}", err=True)
            raise typer.Exit(code=1)
        repository.set_listing_active(conn, listing_id, False)
    finally:
        conn.close()
    typer.echo(f"Unlinked listing {listing_id}.")


@app.command("history")
def history_command(
    ctx: typer.Context,
    book_id: int = typer.Argument(...),
    days: int = typer.Option(None, "--days", help="Restrict to the last N days"),
    store_slug: str = typer.Option(None, "--store", help="Restrict to one store slug"),
) -> None:
    conn = _connect(ctx)
    try:
        _require_book(conn, book_id)
        rows = repository.observations_for_book(conn, book_id, days=days, store_slug=store_slug)
        # observations_for_book returns raw observation columns only (no
        # store_slug) -- look it up per listing rather than touching that
        # query, which is shared with other callers scoped to one book.
        store_by_listing = {
            listing.id: listing.store_slug
            for listing in repository.list_listings_for_book(conn, book_id)
        }
    finally:
        conn.close()

    if not rows:
        typer.echo("No observations.")
        return

    typer.echo(f"{'DATE':<12} {'STORE':<15} {'PRICE':<15} {'STATUS':<12}")
    for row in rows:
        store = store_by_listing.get(row["listing_id"], "")
        # FR-22: a failed observation must show its status explicitly in the
        # price column, never a blank cell that could be misread as $0.
        price = (
            _format_price(row["price_cents"], row["currency"])
            if row["status"] == "ok"
            else row["status"]
        )
        typer.echo(f"{row['observed_on']:<12} {store:<15} {price:<15} {row['status']:<12}")


@app.command("export")
def export_command(
    ctx: typer.Context,
    csv_path: str = typer.Option(..., "--csv", help="Output CSV file path"),
    book: int = typer.Option(None, "--book", help="Restrict export to one book id"),
    since: str = typer.Option(
        None, "--since", help="Restrict to observations on/after this date (YYYY-MM-DD)"
    ),
) -> None:
    conn = _connect(ctx)
    try:
        rows = repository.export_observations(conn, book_id=book, since=since)
    finally:
        conn.close()

    fieldnames = [
        "book_title", "isbn13", "store_slug", "observed_on", "status", "price_cents", "currency",
    ]
    out_path = Path(csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    typer.echo(f"Exported {len(rows)} observations to {csv_path}")
