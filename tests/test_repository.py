import sqlite3
from datetime import date

import pytest

from spinewatch.db import init_db
from spinewatch.models import Listing, Observation, ObservationStatus
from spinewatch.repository import (
    active_listings,
    add_book,
    add_listing,
    delete_book,
    delete_listing,
    export_observations,
    find_listing,
    get_book,
    get_listing,
    latest_observations_by_listing,
    link_listing,
    list_books,
    list_listings_for_book,
    list_stores,
    listings_due_today,
    observations_for_book,
    set_book_active,
    set_listing_active,
    set_store_enabled,
    upsert_observation,
    upsert_store,
)


@pytest.fixture
def conn():
    connection = init_db(":memory:")
    yield connection
    connection.close()


# --- books -------------------------------------------------------------

def test_add_book_then_get_book_round_trips(conn):
    book = add_book(conn, title="Clean Code", isbn13="9780132350884", author="Robert Martin")
    fetched = get_book(conn, book.id)
    assert fetched.title == "Clean Code"
    assert fetched.isbn13 == "9780132350884"
    assert fetched.active is True


def test_list_books_returns_all_by_default(conn):
    add_book(conn, title="Book One")
    add_book(conn, title="Book Two")
    assert len(list_books(conn)) == 2


def test_list_books_active_only_excludes_disabled(conn):
    active = add_book(conn, title="Active Book")
    disabled = add_book(conn, title="Disabled Book")
    set_book_active(conn, disabled.id, False)

    result = list_books(conn, active_only=True)

    assert [b.id for b in result] == [active.id]


def test_delete_book_cascades_to_listings_and_observations(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="Doomed Book")
    listing = add_listing(
        conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/p/1")
    )
    upsert_observation(
        conn,
        Observation(
            id=None,
            listing_id=listing.id,
            observed_on="2026-07-23",
            observed_at="2026-07-23T00:00:00",
            status=ObservationStatus.OK,
            price_cents=1999,
            currency="BRL",
        ),
    )

    delete_book(conn, book.id)

    assert get_book(conn, book.id) is None
    assert get_listing(conn, listing.id) is None
    assert observations_for_book(conn, book.id) == []


# --- stores --------------------------------------------------------------

def test_upsert_store_then_list_stores(conn):
    upsert_store(conn, "amazon_br", "Amazon Brazil")
    rows = list_stores(conn)
    assert len(rows) == 1
    assert rows[0]["slug"] == "amazon_br"
    assert rows[0]["name"] == "Amazon Brazil"
    assert rows[0]["enabled"] == 1


def test_upsert_store_is_idempotent_on_slug(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    upsert_store(conn, "ml", "Mercado Livre (renamed)")
    rows = list_stores(conn)
    assert len(rows) == 1
    assert rows[0]["name"] == "Mercado Livre (renamed)"


def test_set_store_enabled_toggles_flag(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    set_store_enabled(conn, "ml", False)
    rows = list_stores(conn)
    assert rows[0]["enabled"] == 0


# --- listings --------------------------------------------------------------

def test_add_listing_then_get_listing_round_trips(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    created = add_listing(
        conn,
        Listing(
            id=None,
            book_id=book.id,
            store_slug="ml",
            url="https://x/p/1",
            store_product_id="MLB123",
            store_title="A Book - Paperback",
        ),
    )
    fetched = get_listing(conn, created.id)
    assert fetched.url == "https://x/p/1"
    assert fetched.store_product_id == "MLB123"


def test_list_listings_for_book_returns_only_that_books_listings(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book_a = add_book(conn, title="Book A")
    book_b = add_book(conn, title="Book B")
    add_listing(conn, Listing(id=None, book_id=book_a.id, store_slug="ml", url="https://x/a"))
    add_listing(conn, Listing(id=None, book_id=book_b.id, store_slug="ml", url="https://x/b"))

    result = list_listings_for_book(conn, book_a.id)

    assert [listing.url for listing in result] == ["https://x/a"]


def test_two_listings_same_book_and_store_coexist_with_different_urls(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/paperback"))
    add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/hardcover"))

    assert len(list_listings_for_book(conn, book.id)) == 2


def test_add_listing_rejects_exact_duplicate(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/p/1"))

    with pytest.raises(sqlite3.IntegrityError):
        add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/p/1"))


def test_delete_listing_preserves_book_and_removes_listing(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    listing = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/p/1"))

    delete_listing(conn, listing.id)

    assert get_listing(conn, listing.id) is None
    assert get_book(conn, book.id) is not None


# --- observations: the idempotency and integrity keystones ------------------

def test_upsert_observation_twice_same_day_yields_one_row_and_second_wins(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    listing = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/p/1"))

    upsert_observation(
        conn,
        Observation(
            id=None,
            listing_id=listing.id,
            observed_on="2026-07-23",
            observed_at="2026-07-23T03:17:00",
            status=ObservationStatus.BLOCKED,
        ),
    )
    upsert_observation(
        conn,
        Observation(
            id=None,
            listing_id=listing.id,
            observed_on="2026-07-23",
            observed_at="2026-07-23T09:00:00",
            status=ObservationStatus.OK,
            price_cents=2999,
            currency="BRL",
        ),
    )

    rows = observations_for_book(conn, book.id)
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["price_cents"] == 2999


def test_upsert_observation_rejects_ok_status_without_price(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    listing = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/p/1"))

    with pytest.raises(sqlite3.IntegrityError):
        upsert_observation(
            conn,
            Observation(
                id=None,
                listing_id=listing.id,
                observed_on="2026-07-23",
                observed_at="2026-07-23T03:17:00",
                status=ObservationStatus.OK,
                price_cents=None,
            ),
        )


def test_observations_for_book_filters_by_store(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    upsert_store(conn, "amazon_br", "Amazon Brazil")
    book = add_book(conn, title="A Book")
    ml_listing = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/ml"))
    az_listing = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="amazon_br", url="https://x/az"))
    for listing, price in ((ml_listing, 1000), (az_listing, 2000)):
        upsert_observation(
            conn,
            Observation(
                id=None,
                listing_id=listing.id,
                observed_on="2026-07-23",
                observed_at="2026-07-23T03:17:00",
                status=ObservationStatus.OK,
                price_cents=price,
                currency="BRL",
            ),
        )

    result = observations_for_book(conn, book.id, store_slug="amazon_br")

    assert len(result) == 1
    assert result[0]["price_cents"] == 2000


def test_observations_for_book_respects_days_window(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    listing = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/p/1"))
    for day in ("2026-07-01", "2026-07-20", "2026-07-23"):
        upsert_observation(
            conn,
            Observation(
                id=None,
                listing_id=listing.id,
                observed_on=day,
                observed_at=f"{day}T03:17:00",
                status=ObservationStatus.OK,
                price_cents=1000,
                currency="BRL",
            ),
        )

    result = observations_for_book(conn, book.id, days=5, today="2026-07-23")

    assert [r["observed_on"] for r in result] == ["2026-07-23", "2026-07-20"]


# --- listings_due_today ------------------------------------------------

def test_listings_due_today_excludes_already_observed(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    observed = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/observed"))
    pending = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/pending"))
    today = date.today().isoformat()
    upsert_observation(
        conn,
        Observation(
            id=None,
            listing_id=observed.id,
            observed_on=today,
            observed_at=f"{today}T03:17:00",
            status=ObservationStatus.OK,
            price_cents=1000,
            currency="BRL",
        ),
    )

    due = listings_due_today(conn, today=today)

    assert [listing.id for listing in due] == [pending.id]


def test_listings_due_today_excludes_inactive_book_and_disabled_store(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    upsert_store(conn, "amazon_br", "Amazon Brazil")
    set_store_enabled(conn, "amazon_br", False)
    active_book = add_book(conn, title="Active Book")
    inactive_book = add_book(conn, title="Inactive Book")
    set_book_active(conn, inactive_book.id, False)

    add_listing(conn, Listing(id=None, book_id=inactive_book.id, store_slug="ml", url="https://x/1"))
    add_listing(conn, Listing(id=None, book_id=active_book.id, store_slug="amazon_br", url="https://x/2"))
    expected = add_listing(conn, Listing(id=None, book_id=active_book.id, store_slug="ml", url="https://x/3"))

    due = listings_due_today(conn)

    assert [listing.id for listing in due] == [expected.id]


def test_listings_due_today_honors_only_store_and_only_book_filters(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    upsert_store(conn, "amazon_br", "Amazon Brazil")
    book_a = add_book(conn, title="Book A")
    book_b = add_book(conn, title="Book B")
    listing_a_ml = add_listing(conn, Listing(id=None, book_id=book_a.id, store_slug="ml", url="https://x/a-ml"))
    add_listing(conn, Listing(id=None, book_id=book_a.id, store_slug="amazon_br", url="https://x/a-az"))
    add_listing(conn, Listing(id=None, book_id=book_b.id, store_slug="ml", url="https://x/b-ml"))

    due = listings_due_today(conn, only_store="ml", only_book=book_a.id)

    assert [listing.id for listing in due] == [listing_a_ml.id]


# --- active_listings -----------------------------------------------------

def test_active_listings_includes_already_observed_listings(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    observed = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/observed"))
    pending = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/pending"))
    today = date.today().isoformat()
    upsert_observation(
        conn,
        Observation(
            id=None,
            listing_id=observed.id,
            observed_on=today,
            observed_at=f"{today}T03:17:00",
            status=ObservationStatus.OK,
            price_cents=1000,
            currency="BRL",
        ),
    )

    result = active_listings(conn)

    assert {listing.id for listing in result} == {observed.id, pending.id}


def test_active_listings_excludes_inactive_book_and_disabled_store(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    upsert_store(conn, "amazon_br", "Amazon Brazil")
    set_store_enabled(conn, "amazon_br", False)
    active_book = add_book(conn, title="Active Book")
    inactive_book = add_book(conn, title="Inactive Book")
    set_book_active(conn, inactive_book.id, False)

    add_listing(conn, Listing(id=None, book_id=inactive_book.id, store_slug="ml", url="https://x/1"))
    add_listing(conn, Listing(id=None, book_id=active_book.id, store_slug="amazon_br", url="https://x/2"))
    expected = add_listing(conn, Listing(id=None, book_id=active_book.id, store_slug="ml", url="https://x/3"))

    result = active_listings(conn)

    assert [listing.id for listing in result] == [expected.id]


def test_active_listings_honors_only_store_and_only_book_filters(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    upsert_store(conn, "amazon_br", "Amazon Brazil")
    book_a = add_book(conn, title="Book A")
    book_b = add_book(conn, title="Book B")
    listing_a_ml = add_listing(conn, Listing(id=None, book_id=book_a.id, store_slug="ml", url="https://x/a-ml"))
    add_listing(conn, Listing(id=None, book_id=book_a.id, store_slug="amazon_br", url="https://x/a-az"))
    add_listing(conn, Listing(id=None, book_id=book_b.id, store_slug="ml", url="https://x/b-ml"))

    result = active_listings(conn, only_store="ml", only_book=book_a.id)

    assert [listing.id for listing in result] == [listing_a_ml.id]


# --- find_listing / set_listing_active ------------------------------------

def test_find_listing_returns_matching_row(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    listing = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/1"))

    found = find_listing(conn, book.id, "ml", "https://x/1")

    assert found is not None
    assert found.id == listing.id


def test_find_listing_returns_none_when_no_match(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/1"))

    assert find_listing(conn, book.id, "ml", "https://x/other") is None
    assert find_listing(conn, book.id, "amazon_br", "https://x/1") is None


def test_set_listing_active_flips_flag_without_touching_other_listings(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    listing_a = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/a"))
    listing_b = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/b"))

    set_listing_active(conn, listing_a.id, False)

    assert get_listing(conn, listing_a.id).active is False
    assert get_listing(conn, listing_b.id).active is True

    set_listing_active(conn, listing_a.id, True)

    assert get_listing(conn, listing_a.id).active is True


# --- link_listing ----------------------------------------------------------

def test_link_listing_creates_new_listing_when_none_exists(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")

    listing, created = link_listing(conn, book_id=book.id, store_slug="ml", url="https://x/1")

    assert created is True
    assert listing.book_id == book.id
    assert listing.active is True


def test_link_listing_reactivates_existing_inactive_listing(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    existing = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/1"))
    set_listing_active(conn, existing.id, False)

    listing, created = link_listing(
        conn, book_id=book.id, store_slug="ml", url="https://x/1", store_title="New Title"
    )

    assert created is False
    assert listing.id == existing.id
    assert listing.active is True
    assert listing.store_title == "New Title"


def test_link_listing_reports_not_created_when_already_active(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    existing = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/1"))

    listing, created = link_listing(conn, book_id=book.id, store_slug="ml", url="https://x/1")

    assert created is False
    assert listing.id == existing.id
    assert listing.active is True


# --- latest_observations_by_listing -----------------------------------------

def test_latest_observations_by_listing_picks_most_recent_observed_on(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    listing = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/1"))
    upsert_observation(
        conn,
        Observation(
            id=None, listing_id=listing.id, observed_on="2026-07-27", observed_at="2026-07-27T03:17:00",
            status=ObservationStatus.OK, price_cents=4000, currency="BRL",
        ),
    )
    upsert_observation(
        conn,
        Observation(
            id=None, listing_id=listing.id, observed_on="2026-07-28", observed_at="2026-07-28T03:17:00",
            status=ObservationStatus.OK, price_cents=4590, currency="BRL",
        ),
    )

    latest = latest_observations_by_listing(conn)

    assert latest[listing.id]["observed_on"] == "2026-07-28"
    assert latest[listing.id]["price_cents"] == 4590


def test_latest_observations_by_listing_omits_listings_with_no_observations(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="A Book")
    listing = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/1"))

    latest = latest_observations_by_listing(conn)

    assert listing.id not in latest


# --- export_observations -------------------------------------------------

def test_export_observations_with_no_filters_returns_everything(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book_a = add_book(conn, title="Book A", isbn13="9780132350884")
    book_b = add_book(conn, title="Book B")
    listing_a = add_listing(conn, Listing(id=None, book_id=book_a.id, store_slug="ml", url="https://x/a"))
    listing_b = add_listing(conn, Listing(id=None, book_id=book_b.id, store_slug="ml", url="https://x/b"))
    upsert_observation(
        conn,
        Observation(
            id=None, listing_id=listing_a.id, observed_on="2026-07-20",
            observed_at="2026-07-20T00:00:00", status=ObservationStatus.OK,
            price_cents=1000, currency="BRL",
        ),
    )
    upsert_observation(
        conn,
        Observation(
            id=None, listing_id=listing_b.id, observed_on="2026-07-21",
            observed_at="2026-07-21T00:00:00", status=ObservationStatus.BLOCKED,
        ),
    )

    rows = export_observations(conn)

    assert len(rows) == 2
    assert {row["book_title"] for row in rows} == {"Book A", "Book B"}
    for row in rows:
        assert set(row.keys()) == {
            "book_title", "isbn13", "store_slug", "observed_on", "status",
            "price_cents", "currency",
        }
    by_title = {row["book_title"]: row for row in rows}
    assert by_title["Book A"]["isbn13"] == "9780132350884"
    assert by_title["Book A"]["price_cents"] == 1000
    assert by_title["Book B"]["status"] == "blocked"
    assert by_title["Book B"]["price_cents"] is None


def test_export_observations_book_id_filter_restricts_to_one_book(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book_a = add_book(conn, title="Book A")
    book_b = add_book(conn, title="Book B")
    listing_a = add_listing(conn, Listing(id=None, book_id=book_a.id, store_slug="ml", url="https://x/a"))
    listing_b = add_listing(conn, Listing(id=None, book_id=book_b.id, store_slug="ml", url="https://x/b"))
    for listing in (listing_a, listing_b):
        upsert_observation(
            conn,
            Observation(
                id=None, listing_id=listing.id, observed_on="2026-07-20",
                observed_at="2026-07-20T00:00:00", status=ObservationStatus.OK,
                price_cents=1000, currency="BRL",
            ),
        )

    rows = export_observations(conn, book_id=book_a.id)

    assert len(rows) == 1
    assert rows[0]["book_title"] == "Book A"


def test_export_observations_since_filter_restricts_to_matching_dates(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book = add_book(conn, title="Book A")
    listing = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/a"))
    for day in ("2026-07-10", "2026-07-20", "2026-07-25"):
        upsert_observation(
            conn,
            Observation(
                id=None, listing_id=listing.id, observed_on=day,
                observed_at=f"{day}T00:00:00", status=ObservationStatus.OK,
                price_cents=1000, currency="BRL",
            ),
        )

    rows = export_observations(conn, since="2026-07-20")

    assert [row["observed_on"] for row in rows] == ["2026-07-20", "2026-07-25"]


def test_export_observations_book_id_and_since_compose(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    book_a = add_book(conn, title="Book A")
    book_b = add_book(conn, title="Book B")
    listing_a = add_listing(conn, Listing(id=None, book_id=book_a.id, store_slug="ml", url="https://x/a"))
    listing_b = add_listing(conn, Listing(id=None, book_id=book_b.id, store_slug="ml", url="https://x/b"))
    for listing in (listing_a, listing_b):
        for day in ("2026-07-10", "2026-07-25"):
            upsert_observation(
                conn,
                Observation(
                    id=None, listing_id=listing.id, observed_on=day,
                    observed_at=f"{day}T00:00:00", status=ObservationStatus.OK,
                    price_cents=1000, currency="BRL",
                ),
            )

    rows = export_observations(conn, book_id=book_a.id, since="2026-07-20")

    assert len(rows) == 1
    assert rows[0]["book_title"] == "Book A"
    assert rows[0]["observed_on"] == "2026-07-25"


def test_export_observations_orders_ties_by_store_slug(conn):
    upsert_store(conn, "ml", "Mercado Livre")
    upsert_store(conn, "amazon", "Amazon")
    book = add_book(conn, title="Book A")
    listing_ml = add_listing(conn, Listing(id=None, book_id=book.id, store_slug="ml", url="https://x/a"))
    listing_amazon = add_listing(
        conn, Listing(id=None, book_id=book.id, store_slug="amazon", url="https://x/b")
    )
    # Same book, same observed_on, different stores: insert in an order that
    # would surface a missing tiebreaker if one existed.
    for listing in (listing_ml, listing_amazon):
        upsert_observation(
            conn,
            Observation(
                id=None, listing_id=listing.id, observed_on="2026-07-20",
                observed_at="2026-07-20T00:00:00", status=ObservationStatus.OK,
                price_cents=1000, currency="BRL",
            ),
        )

    rows = export_observations(conn, book_id=book.id)

    assert [row["store_slug"] for row in rows] == ["amazon", "ml"]
