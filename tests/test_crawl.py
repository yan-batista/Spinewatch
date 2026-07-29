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

    def __init__(self, responses: dict):
        self.responses = responses
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

    summary = run_crawl(conn, fetcher, today="2026-07-28", sleep_fn=lambda s: None)

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
    run_crawl(conn, fetcher, today=today, sleep_fn=lambda s: None)
    rows = _all_observations(conn)
    assert len(rows) == 1
    assert rows[0]["status"] == "blocked"

    # same-day rerun without force: already observed today, so nothing to do.
    run_crawl(conn, fetcher, today=today, sleep_fn=lambda s: None)
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
    summary = run_crawl(conn, fetcher, sleep_fn=lambda s: None)

    assert summary.listings_attempted == 4
    assert summary.status_counts["blocked"] == 2
    assert summary.status_counts["ok"] == 2


# --- CrawlSummary.succeeded ------------------------------------------------

def test_succeeded_is_false_when_every_attempted_listing_fails(conn, monkeypatch):
    slug = "store_a"
    repository.upsert_store(conn, slug, slug)
    fake_store = FakeStore(slug)
    _install_fake_stores(monkeypatch, {slug: fake_store})
    listing = _due_listing(conn, slug, "https://x/1")
    fetcher = FakeFetcher({listing.url: BlockedError("nope")})

    summary = run_crawl(conn, fetcher, sleep_fn=lambda s: None)

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

    summary = run_crawl(conn, fetcher, sleep_fn=lambda s: None)

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
