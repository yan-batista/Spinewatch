"""Assisted-search fallback chain: isbn13 -> title -> alt_title.

Plain library module (NFR-7), same shape as crawl.py — no Typer, no
printing. `cli.py`'s `books search` command wraps `find_candidates` and
handles all I/O/exit codes.
"""

from __future__ import annotations

from spinewatch.fetching.base import Fetcher
from spinewatch.models import Book, Candidate
from spinewatch.stores.base import Store


def find_candidates(fetcher: Fetcher, store: Store, book: Book) -> tuple[list[Candidate], str]:
    """Try isbn13, then title, then alt_title; stop at the first non-empty result.

    Returns `(candidates, query_used)`. If every query is absent or yields
    nothing, returns `([], "")` — not an error, just nothing found.

    A `SearchNotSupported` from `store.search_url` propagates uncaught; the
    caller (the CLI) is responsible for that message.
    """
    for query in (book.isbn13, book.title, book.alt_title):
        if not query:
            continue
        url = store.search_url(query)
        result = fetcher.fetch(url)
        candidates = store.parse_search_results(result.html, query)
        if candidates:
            return candidates, query
    return [], ""
