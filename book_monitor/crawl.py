"""Daily crawl orchestration: selection -> fetch -> parse -> observation.

Plain library module (NFR-7) — no Typer imports, no printing. `cli.py`'s
`books crawl` command wraps `run_crawl` and handles all I/O/exit codes.
"""

from __future__ import annotations

import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from book_monitor import repository, stores
from book_monitor.errors import BlockedError, NotFoundError, ParseError, UnavailableError
from book_monitor.fetching.base import Fetcher
from book_monitor.models import FetchResult, Listing, Observation, ObservationStatus
from book_monitor.stores.base import Store


@dataclass
class CrawlSummary:
    status_counts: dict[str, int]
    listings_attempted: int
    duration_seconds: float
    escalations_used: int = 0

    @property
    def succeeded(self) -> bool:
        return self.listings_attempted == 0 or self.status_counts.get("ok", 0) > 0


def run_crawl(
    conn: sqlite3.Connection,
    fetcher: Fetcher,
    *,
    only_store: str | None = None,
    only_book: int | None = None,
    force: bool = False,
    dry_run: bool = False,
    today: str | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> CrawlSummary:
    start = time.monotonic()
    stores.sync_registry(conn)
    today = today or date.today().isoformat()

    if force:
        listings = repository.active_listings(conn, only_store=only_store, only_book=only_book)
    else:
        listings = repository.listings_due_today(
            conn, only_store=only_store, only_book=only_book, today=today
        )

    grouped: dict[str, list[Listing]] = {}
    for listing in listings:
        grouped.setdefault(listing.store_slug, []).append(listing)

    status_counts: dict[str, int] = {}
    listings_attempted = 0

    for store_slug, group in grouped.items():
        random.shuffle(group)
        store = stores.get_store(store_slug)
        for i, listing in enumerate(group):
            if i > 0:
                sleep_fn(random.uniform(*store.request_delay))

            observation = _crawl_one(listing, fetcher, store, today=today)
            listings_attempted += 1
            status = observation.status.value

            if not dry_run:
                try:
                    repository.upsert_observation(conn, observation)
                except Exception:  # noqa: BLE001 - a write failure is this listing's outcome, not a crawl abort
                    status = ObservationStatus.ERROR.value

            status_counts[status] = status_counts.get(status, 0) + 1

    return CrawlSummary(
        status_counts=status_counts,
        listings_attempted=listings_attempted,
        duration_seconds=time.monotonic() - start,
    )


def _crawl_one(listing: Listing, fetcher: Fetcher, store: Store, *, today: str) -> Observation:
    observed_at = datetime.now().isoformat()
    result: FetchResult | None = None
    try:
        result = fetcher.fetch(listing.url)
        parsed = store.parse_listing(result.html, result.final_url)
    except BlockedError as exc:
        return _failed_observation(listing, ObservationStatus.BLOCKED, exc, result, today, observed_at)
    except NotFoundError as exc:
        return _failed_observation(listing, ObservationStatus.NOT_FOUND, exc, result, today, observed_at)
    except UnavailableError as exc:
        return _failed_observation(listing, ObservationStatus.UNAVAILABLE, exc, result, today, observed_at)
    except ParseError as exc:
        return _failed_observation(listing, ObservationStatus.PARSE_ERROR, exc, result, today, observed_at)
    except Exception as exc:  # noqa: BLE001 - catch-all per FR-17/NFR-10
        return _failed_observation(listing, ObservationStatus.ERROR, exc, result, today, observed_at)

    return Observation(
        id=None,
        listing_id=listing.id,
        observed_on=today,
        observed_at=observed_at,
        status=ObservationStatus.OK,
        price_cents=parsed.price_cents,
        currency=parsed.currency,
        in_stock=parsed.in_stock,
        seller=parsed.seller,
        fetcher=result.fetcher,
        raw_price_text=parsed.raw_price_text,
    )


def _failed_observation(
    listing: Listing,
    status: ObservationStatus,
    exc: Exception,
    result: FetchResult | None,
    today: str,
    observed_at: str,
) -> Observation:
    return Observation(
        id=None,
        listing_id=listing.id,
        observed_on=today,
        observed_at=observed_at,
        status=status,
        # ponytail: no `name` attribute on the Fetcher protocol yet (only
        # HttpFetcher exists) — hardcode "http" when a failure happened
        # before a FetchResult was obtained. Revisit if/when Phase 5 adds a
        # second fetcher implementation.
        fetcher=result.fetcher if result is not None else "http",
        error=str(exc),
    )
