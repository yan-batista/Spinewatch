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

from spinewatch import repository, stores
from spinewatch.errors import BlockedError, NotFoundError, ParseError, UnavailableError
from spinewatch.fetching.base import Fetcher
from spinewatch.fetching.browser import BrowserFetcher
from spinewatch.models import FetchResult, Listing, Observation, ObservationStatus
from spinewatch.stores.base import Store


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
    max_escalations: int | None = None,
    browser_timeout: float = 30.0,
    browser_fetcher_factory: Callable[[], Fetcher] | None = None,
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
    escalations_used = 0
    browser_fetcher: Fetcher | None = None

    def _get_browser_fetcher() -> Fetcher:
        nonlocal browser_fetcher
        if browser_fetcher is None:
            browser_fetcher = (
                browser_fetcher_factory()
                if browser_fetcher_factory is not None
                else BrowserFetcher(timeout=browser_timeout)
            )
        return browser_fetcher

    try:
        for store_slug, group in grouped.items():
            random.shuffle(group)
            store = stores.get_store(store_slug)
            for i, listing in enumerate(group):
                if i > 0:
                    sleep_fn(random.uniform(*store.request_delay))

                def _escalate(listing: Listing = listing, store: Store = store) -> Observation | None:
                    nonlocal escalations_used
                    if not store.allow_browser_fallback:
                        return None
                    if max_escalations is not None and escalations_used >= max_escalations:
                        return None
                    escalations_used += 1
                    return _crawl_one(listing, _get_browser_fetcher(), store, today=today)

                observation = _crawl_one(listing, fetcher, store, today=today, escalate=_escalate)
                listings_attempted += 1
                status = observation.status.value

                if not dry_run:
                    try:
                        repository.upsert_observation(conn, observation)
                    except Exception:  # noqa: BLE001 - a write failure is this listing's outcome, not a crawl abort
                        status = ObservationStatus.ERROR.value

                status_counts[status] = status_counts.get(status, 0) + 1
    finally:
        if browser_fetcher is not None:
            browser_fetcher.close()

    return CrawlSummary(
        status_counts=status_counts,
        listings_attempted=listings_attempted,
        duration_seconds=time.monotonic() - start,
        escalations_used=escalations_used,
    )


def _crawl_one(
    listing: Listing,
    fetcher: Fetcher,
    store: Store,
    *,
    today: str,
    escalate: Callable[[], Observation | None] | None = None,
) -> Observation:
    """Fetch, parse, and map the outcome to an Observation.

    `escalate` (only ever passed for the primary-fetcher attempt, never for
    an escalated one -- see `run_crawl`) is consulted solely on BlockedError:
    it returns a replacement Observation from a browser-fetcher retry, or
    None if escalation isn't available/exhausted, in which case this listing
    is recorded as `blocked` as before. No other exception type escalates.

    `escalate()` itself can raise (e.g. the lazy `BrowserFetcher()` failing to
    launch Chromium) -- that's contained here the same way `run_crawl`
    contains an `upsert_observation` failure: this listing becomes `error`
    instead of the exception aborting the rest of the run.
    """
    observed_at = datetime.now().isoformat()
    result: FetchResult | None = None
    try:
        result = fetcher.fetch(listing.url)
        parsed = store.parse_listing(result.html, result.final_url)
    except BlockedError as exc:
        if escalate is not None:
            try:
                escalated = escalate()
            except Exception as escalation_exc:  # noqa: BLE001 - browser-construction/fetch setup failure is this listing's outcome, not a crawl abort
                return _failed_observation(
                    listing, ObservationStatus.ERROR, escalation_exc, result, today, observed_at, fetcher
                )
            if escalated is not None:
                return escalated
        return _failed_observation(listing, ObservationStatus.BLOCKED, exc, result, today, observed_at, fetcher)
    except NotFoundError as exc:
        return _failed_observation(listing, ObservationStatus.NOT_FOUND, exc, result, today, observed_at, fetcher)
    except UnavailableError as exc:
        return _failed_observation(listing, ObservationStatus.UNAVAILABLE, exc, result, today, observed_at, fetcher)
    except ParseError as exc:
        return _failed_observation(listing, ObservationStatus.PARSE_ERROR, exc, result, today, observed_at, fetcher)
    except Exception as exc:  # noqa: BLE001 - catch-all per FR-17/NFR-10
        return _failed_observation(listing, ObservationStatus.ERROR, exc, result, today, observed_at, fetcher)

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
    fetcher: Fetcher,
) -> Observation:
    return Observation(
        id=None,
        listing_id=listing.id,
        observed_on=today,
        observed_at=observed_at,
        status=status,
        # A failure before a FetchResult was obtained (e.g. BlockedError
        # raised inside fetch() itself) has no result.fetcher to read, so
        # fall back to the fetcher instance's own name.
        fetcher=result.fetcher if result is not None else fetcher.name,
        error=str(exc),
    )
