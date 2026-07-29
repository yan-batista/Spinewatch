import sqlite3

import pytest

from book_monitor import repository, stores
from book_monitor.crawl import run_crawl
from book_monitor.db import init_db
from book_monitor.errors import BlockedError, NotFoundError, ParseError, UnavailableError
from book_monitor.models import FetchResult, Listing, ParsedListing


@pytest.fixture
def conn():
    connection = init_db(":memory:")
    yield connection
    connection.close()


class FakeFetcher:
    """Driven by a dict of url -> FetchResult | Exception."""

    def __init__(self, responses: dict, name: str = "http"):
        self.responses = responses
        self.name = name
        self.calls: list[str] = []
        self.closed = False

    def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        outcome = self.responses[url]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def close(self) -> None:
        self.closed = True


class FakeStore:
    """Driven by a dict of html -> ParsedListing | Exception."""

    def __init__(self, slug: str, request_delay: tuple[float, float] = (0.0, 0.0)):
        self.slug = slug
        self.name = slug
        self.request_delay = request_delay
        self.allow_browser_fallback = True
        self.parse_results: dict = {}
        self.parse_calls: list[tuple[str, str]] = []

    def parse_listing(self, html: str, url: str) -> ParsedListing:
        self.parse_calls.append((html, url))
        outcome = self.parse_results[html]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _due_listing(conn, slug: str, url: str) -> Listing:
    book = repository.add_book(conn, title=f"Book for {url}")
    return repository.add_listing(
        conn, Listing(id=None, book_id=book.id, store_slug=slug, url=url)
    )


def _install_fake_stores(monkeypatch, store_map: dict[str, FakeStore]) -> None:
    monkeypatch.setattr(stores, "get_store", lambda slug: store_map[slug])


def _all_observations(conn):
    return conn.execute("SELECT * FROM observations").fetchall()


# --- exception -> status mapping ----------------------------------------

def test_each_exception_type_maps_to_its_documented_status_and_only_ok_has_price(conn, monkeypatch):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    _install_fake_stores(monkeypatch, {slug: fake_store})

    listings = {
        "blocked": _due_listing(conn, slug, "https://x/blocked"),
        "not_found": _due_listing(conn, slug, "https://x/not-found"),
        "unavailable": _due_listing(conn, slug, "https://x/unavailable"),
        "parse_error": _due_listing(conn, slug, "https://x/parse-error"),
        "error": _due_listing(conn, slug, "https://x/error"),
        "ok": _due_listing(conn, slug, "https://x/ok"),
    }

    responses = {
        listings["blocked"].url: BlockedError("blocked"),
        listings["not_found"].url: FetchResult(html="nf", status_code=200, final_url=listings["not_found"].url, fetcher="http"),
        listings["unavailable"].url: FetchResult(html="ua", status_code=200, final_url=listings["unavailable"].url, fetcher="http"),
        listings["parse_error"].url: FetchResult(html="pe", status_code=200, final_url=listings["parse_error"].url, fetcher="http"),
        listings["error"].url: RuntimeError("boom"),
        listings["ok"].url: FetchResult(html="ok", status_code=200, final_url=listings["ok"].url, fetcher="http"),
    }
    fake_store.parse_results = {
        "nf": NotFoundError("nf"),
        "ua": UnavailableError("ua"),
        "pe": ParseError("pe"),
        "ok": ParsedListing(price_cents=2500, currency="BRL", in_stock=True, raw_price_text="25,00"),
    }
    fetcher = FakeFetcher(responses)

    # max_escalations=0: this test is about status mapping, not escalation --
    # a BlockedError here should land as "blocked", not trigger a real
    # browser-fallback attempt.
    summary = run_crawl(conn, fetcher, today="2026-07-28", sleep_fn=lambda s: None, max_escalations=0)

    rows_by_listing = {row["listing_id"]: row for row in _all_observations(conn)}
    assert rows_by_listing[listings["blocked"].id]["status"] == "blocked"
    assert rows_by_listing[listings["not_found"].id]["status"] == "not_found"
    assert rows_by_listing[listings["unavailable"].id]["status"] == "unavailable"
    assert rows_by_listing[listings["parse_error"].id]["status"] == "parse_error"
    assert rows_by_listing[listings["error"].id]["status"] == "error"
    assert rows_by_listing[listings["ok"].id]["status"] == "ok"
    assert rows_by_listing[listings["ok"].id]["price_cents"] == 2500
    for key in ("blocked", "not_found", "unavailable", "parse_error", "error"):
        assert rows_by_listing[listings[key].id]["price_cents"] is None
    assert summary.status_counts == {
        "blocked": 1,
        "not_found": 1,
        "unavailable": 1,
        "parse_error": 1,
        "error": 1,
        "ok": 1,
    }


# --- basic multi-store crawl ---------------------------------------------

def test_successful_crawl_across_two_stores_produces_one_observation_per_listing(conn, monkeypatch):
    store_map = {slug: FakeStore(slug) for slug in ("store_a", "store_b")}
    for slug in store_map:
        repository.upsert_store(conn, slug, slug)
    _install_fake_stores(monkeypatch, store_map)

    responses = {}
    listings = []
    for slug in store_map:
        for i in range(2):
            listing = _due_listing(conn, slug, f"https://{slug}/item-{i}")
            listings.append(listing)
            html = f"html-{slug}-{i}"
            responses[listing.url] = FetchResult(html=html, status_code=200, final_url=listing.url, fetcher="http")
            store_map[slug].parse_results[html] = ParsedListing(
                price_cents=1000 + i, currency="BRL", in_stock=True
            )

    today = "2026-07-28"
    fetcher = FakeFetcher(responses)
    summary = run_crawl(conn, fetcher, today=today, sleep_fn=lambda s: None)

    rows = _all_observations(conn)
    assert len(rows) == 4
    assert all(row["observed_on"] == today for row in rows)
    assert summary.listings_attempted == 4
    assert summary.status_counts["ok"] == 4


# --- idempotency / force --------------------------------------------------

def test_same_day_rerun_is_idempotent_and_force_lets_a_failed_listing_succeed(conn, monkeypatch):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    _install_fake_stores(monkeypatch, {slug: fake_store})

    listing = _due_listing(conn, slug, "https://x/item")
    today = "2026-07-28"

    fetcher = FakeFetcher({listing.url: BlockedError("blocked")})
    run_crawl(conn, fetcher, today=today, sleep_fn=lambda s: None, max_escalations=0)
    rows = _all_observations(conn)
    assert len(rows) == 1
    assert rows[0]["status"] == "blocked"

    # same-day rerun without force: already observed today, so nothing to do.
    run_crawl(conn, fetcher, today=today, sleep_fn=lambda s: None, max_escalations=0)
    rows = _all_observations(conn)
    assert len(rows) == 1
    assert rows[0]["status"] == "blocked"

    # forced rerun: fetcher now succeeds, upsert overwrites the same row.
    fake_store.parse_results["ok-html"] = ParsedListing(price_cents=1500, currency="BRL", in_stock=True)
    fetcher2 = FakeFetcher({listing.url: FetchResult(html="ok-html", status_code=200, final_url=listing.url, fetcher="http")})
    run_crawl(conn, fetcher2, today=today, force=True, sleep_fn=lambda s: None)

    rows = _all_observations(conn)
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["price_cents"] == 1500


def test_default_run_skips_already_observed_listing_but_force_includes_it(conn, monkeypatch):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    _install_fake_stores(monkeypatch, {slug: fake_store})

    listing = _due_listing(conn, slug, "https://x/item")
    today = "2026-07-28"
    fake_store.parse_results["html"] = ParsedListing(price_cents=1000, currency="BRL", in_stock=True)
    fetcher = FakeFetcher({listing.url: FetchResult(html="html", status_code=200, final_url=listing.url, fetcher="http")})

    first = run_crawl(conn, fetcher, today=today, sleep_fn=lambda s: None)
    assert first.listings_attempted == 1

    skipped = run_crawl(conn, fetcher, today=today, sleep_fn=lambda s: None)
    assert skipped.listings_attempted == 0
    assert skipped.succeeded is True  # nothing selected is not a failure

    forced = run_crawl(conn, fetcher, today=today, force=True, sleep_fn=lambda s: None)
    assert forced.listings_attempted == 1


# --- per-listing failure containment (FR-17) ------------------------------

def test_one_store_failing_every_listing_does_not_block_the_other_store(conn, monkeypatch):
    store_map = {slug: FakeStore(slug) for slug in ("store_a", "store_b")}
    for slug in store_map:
        repository.upsert_store(conn, slug, slug)
    _install_fake_stores(monkeypatch, store_map)

    responses = {}
    a_listings = [_due_listing(conn, "store_a", f"https://store_a/{i}") for i in range(2)]
    for listing in a_listings:
        responses[listing.url] = BlockedError("blocked")

    b_listings = [_due_listing(conn, "store_b", f"https://store_b/{i}") for i in range(2)]
    for i, listing in enumerate(b_listings):
        html = f"b-html-{i}"
        responses[listing.url] = FetchResult(html=html, status_code=200, final_url=listing.url, fetcher="http")
        store_map["store_b"].parse_results[html] = ParsedListing(
            price_cents=1000 + i, currency="BRL", in_stock=True
        )

    fetcher = FakeFetcher(responses)
    summary = run_crawl(conn, fetcher, sleep_fn=lambda s: None, max_escalations=0)

    assert summary.listings_attempted == 4
    assert summary.status_counts["blocked"] == 2
    assert summary.status_counts["ok"] == 2


# --- observation-write failure containment --------------------------------

def test_upsert_observation_failure_for_one_listing_is_counted_as_error_and_does_not_abort_the_run(
    conn, monkeypatch
):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    _install_fake_stores(monkeypatch, {slug: fake_store})

    good_listing = _due_listing(conn, slug, "https://x/good")
    bad_listing = _due_listing(conn, slug, "https://x/bad")
    fake_store.parse_results["good-html"] = ParsedListing(
        price_cents=1000, currency="BRL", in_stock=True
    )
    fake_store.parse_results["bad-html"] = ParsedListing(
        price_cents=2000, currency="BRL", in_stock=True
    )
    fetcher = FakeFetcher(
        {
            good_listing.url: FetchResult(
                html="good-html", status_code=200, final_url=good_listing.url, fetcher="http"
            ),
            bad_listing.url: FetchResult(
                html="bad-html", status_code=200, final_url=bad_listing.url, fetcher="http"
            ),
        }
    )

    real_upsert = repository.upsert_observation

    def _flaky_upsert(conn, observation):
        if observation.listing_id == bad_listing.id:
            raise sqlite3.IntegrityError("simulated write failure")
        return real_upsert(conn, observation)

    monkeypatch.setattr(repository, "upsert_observation", _flaky_upsert)

    summary = run_crawl(conn, fetcher, today="2026-07-28", sleep_fn=lambda s: None)

    assert summary.listings_attempted == 2
    assert summary.status_counts == {"ok": 1, "error": 1}
    rows_by_listing = {row["listing_id"]: row for row in _all_observations(conn)}
    assert good_listing.id in rows_by_listing
    assert rows_by_listing[good_listing.id]["status"] == "ok"
    assert bad_listing.id not in rows_by_listing


# --- CrawlSummary.succeeded ------------------------------------------------

def test_succeeded_is_false_when_every_attempted_listing_fails(conn, monkeypatch):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    _install_fake_stores(monkeypatch, {slug: fake_store})
    listing = _due_listing(conn, slug, "https://x/1")
    fetcher = FakeFetcher({listing.url: BlockedError("nope")})

    summary = run_crawl(conn, fetcher, sleep_fn=lambda s: None, max_escalations=0)

    assert summary.listings_attempted == 1
    assert summary.succeeded is False


def test_succeeded_is_true_when_at_least_one_listing_is_ok(conn, monkeypatch):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    _install_fake_stores(monkeypatch, {slug: fake_store})
    ok_listing = _due_listing(conn, slug, "https://x/ok")
    bad_listing = _due_listing(conn, slug, "https://x/bad")
    fake_store.parse_results["ok-html"] = ParsedListing(price_cents=500, currency="BRL", in_stock=True)
    fetcher = FakeFetcher(
        {
            ok_listing.url: FetchResult(html="ok-html", status_code=200, final_url=ok_listing.url, fetcher="http"),
            bad_listing.url: BlockedError("nope"),
        }
    )

    summary = run_crawl(conn, fetcher, sleep_fn=lambda s: None, max_escalations=0)

    assert summary.succeeded is True


# --- dry run ----------------------------------------------------------------

def test_dry_run_exercises_fetch_and_parse_but_writes_no_observations(conn, monkeypatch):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    _install_fake_stores(monkeypatch, {slug: fake_store})
    listing = _due_listing(conn, slug, "https://x/1")
    fake_store.parse_results["html"] = ParsedListing(price_cents=1000, currency="BRL", in_stock=True)
    fetcher = FakeFetcher({listing.url: FetchResult(html="html", status_code=200, final_url=listing.url, fetcher="http")})

    summary = run_crawl(conn, fetcher, dry_run=True, sleep_fn=lambda s: None)

    assert fetcher.calls == [listing.url]
    assert fake_store.parse_calls == [("html", listing.url)]
    assert summary.listings_attempted == 1
    assert summary.status_counts == {"ok": 1}
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0


# --- politeness delay (FR-19) ------------------------------------------------

def test_sleep_fn_called_between_same_store_requests_but_not_between_stores(conn, monkeypatch):
    store_map = {slug: FakeStore(slug, request_delay=(0.1, 0.1)) for slug in ("store_a", "store_b")}
    for slug in store_map:
        repository.upsert_store(conn, slug, slug)
    _install_fake_stores(monkeypatch, store_map)

    responses = {}
    a_listings = [_due_listing(conn, "store_a", f"https://store_a/{i}") for i in range(3)]
    b_listings = [_due_listing(conn, "store_b", f"https://store_b/{i}") for i in range(2)]
    for listing in a_listings + b_listings:
        html = f"html-{listing.id}"
        responses[listing.url] = FetchResult(html=html, status_code=200, final_url=listing.url, fetcher="http")
        store_map[listing.store_slug].parse_results[html] = ParsedListing(
            price_cents=100, currency="BRL", in_stock=True
        )

    fetcher = FakeFetcher(responses)
    sleep_calls: list[float] = []
    run_crawl(conn, fetcher, sleep_fn=lambda seconds: sleep_calls.append(seconds))

    # 3 listings in store_a -> 2 sleeps; 2 in store_b -> 1 sleep; 3 total.
    # If a sleep ever happened between the two store groups, this would be 4.
    assert len(sleep_calls) == 3


# --- browser-fallback escalation (Phase 5) --------------------------------

def test_blocked_listing_escalates_to_browser_fetcher_and_succeeds(conn, monkeypatch):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    _install_fake_stores(monkeypatch, {slug: fake_store})
    listing = _due_listing(conn, slug, "https://x/item")
    fake_store.parse_results["ok-html"] = ParsedListing(price_cents=1000, currency="BRL", in_stock=True)

    primary = FakeFetcher({listing.url: BlockedError("blocked")})
    browser = FakeFetcher(
        {listing.url: FetchResult(html="ok-html", status_code=200, final_url=listing.url, fetcher="browser")},
        name="browser",
    )

    summary = run_crawl(
        conn,
        primary,
        today="2026-07-28",
        sleep_fn=lambda s: None,
        browser_fetcher_factory=lambda: browser,
    )

    rows = _all_observations(conn)
    assert rows[0]["status"] == "ok"
    assert rows[0]["fetcher"] == "browser"
    assert summary.escalations_used == 1
    assert browser.calls == [listing.url]
    assert browser.closed is True
    assert primary.closed is False  # run_crawl never closes the primary fetcher


def test_blocked_listing_escalates_but_browser_fetch_is_also_blocked(conn, monkeypatch):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    _install_fake_stores(monkeypatch, {slug: fake_store})
    listing = _due_listing(conn, slug, "https://x/item")

    primary = FakeFetcher({listing.url: BlockedError("blocked-primary")})
    browser = FakeFetcher({listing.url: BlockedError("blocked-browser")}, name="browser")

    summary = run_crawl(
        conn,
        primary,
        today="2026-07-28",
        sleep_fn=lambda s: None,
        browser_fetcher_factory=lambda: browser,
    )

    rows = _all_observations(conn)
    assert rows[0]["status"] == "blocked"
    assert rows[0]["fetcher"] == "browser"
    # Escalation happened exactly once for this listing, not twice.
    assert summary.escalations_used == 1
    assert browser.calls == [listing.url]


def test_allow_browser_fallback_false_suppresses_escalation(conn, monkeypatch):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    fake_store.allow_browser_fallback = False
    _install_fake_stores(monkeypatch, {slug: fake_store})
    listing = _due_listing(conn, slug, "https://x/item")

    primary = FakeFetcher({listing.url: BlockedError("blocked")})
    factory_calls: list[int] = []

    def factory():
        factory_calls.append(1)
        return FakeFetcher({}, name="browser")

    summary = run_crawl(
        conn, primary, today="2026-07-28", sleep_fn=lambda s: None, browser_fetcher_factory=factory
    )

    assert factory_calls == []
    assert summary.escalations_used == 0
    rows = _all_observations(conn)
    assert rows[0]["status"] == "blocked"
    assert rows[0]["fetcher"] == "http"


def test_max_escalations_budget_limits_escalations_across_listings(conn, monkeypatch):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    _install_fake_stores(monkeypatch, {slug: fake_store})
    listing1 = _due_listing(conn, slug, "https://x/1")
    listing2 = _due_listing(conn, slug, "https://x/2")
    fake_store.parse_results["h1"] = ParsedListing(price_cents=1, currency="BRL", in_stock=True)
    fake_store.parse_results["h2"] = ParsedListing(price_cents=2, currency="BRL", in_stock=True)

    primary = FakeFetcher(
        {listing1.url: BlockedError("b1"), listing2.url: BlockedError("b2")}
    )
    browser = FakeFetcher(
        {
            listing1.url: FetchResult(html="h1", status_code=200, final_url=listing1.url, fetcher="browser"),
            listing2.url: FetchResult(html="h2", status_code=200, final_url=listing2.url, fetcher="browser"),
        },
        name="browser",
    )
    factory_calls: list[int] = []

    def factory():
        factory_calls.append(1)
        return browser

    summary = run_crawl(
        conn,
        primary,
        today="2026-07-28",
        sleep_fn=lambda s: None,
        max_escalations=1,
        browser_fetcher_factory=factory,
    )

    assert summary.escalations_used == 1
    assert len(factory_calls) == 1
    assert len(browser.calls) == 1
    assert summary.status_counts.get("blocked") == 1
    assert summary.status_counts.get("ok") == 1


def test_parse_error_never_escalates(conn, monkeypatch):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    _install_fake_stores(monkeypatch, {slug: fake_store})
    listing = _due_listing(conn, slug, "https://x/pe")
    fake_store.parse_results["pe-html"] = ParseError("bad parse")

    primary = FakeFetcher(
        {listing.url: FetchResult(html="pe-html", status_code=200, final_url=listing.url, fetcher="http")}
    )
    factory_calls: list[int] = []

    def factory():
        factory_calls.append(1)
        return FakeFetcher({}, name="browser")

    summary = run_crawl(
        conn, primary, today="2026-07-28", sleep_fn=lambda s: None, browser_fetcher_factory=factory
    )

    assert factory_calls == []
    assert summary.escalations_used == 0
    rows = _all_observations(conn)
    assert rows[0]["status"] == "parse_error"


def test_browser_fetcher_factory_never_called_when_nothing_blocks(conn, monkeypatch):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    _install_fake_stores(monkeypatch, {slug: fake_store})
    listing = _due_listing(conn, slug, "https://x/ok")
    fake_store.parse_results["ok-html"] = ParsedListing(price_cents=100, currency="BRL", in_stock=True)

    primary = FakeFetcher(
        {listing.url: FetchResult(html="ok-html", status_code=200, final_url=listing.url, fetcher="http")}
    )
    factory_calls: list[int] = []

    def factory():
        factory_calls.append(1)
        return FakeFetcher({}, name="browser")

    run_crawl(conn, primary, today="2026-07-28", sleep_fn=lambda s: None, browser_fetcher_factory=factory)

    assert factory_calls == []
