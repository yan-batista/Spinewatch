from book_monitor.models import (
    Book,
    Candidate,
    FetchResult,
    Listing,
    Observation,
    ObservationStatus,
    is_valid_isbn10,
    is_valid_isbn13,
    isbn10_to_isbn13,
    normalize_isbn,
    price_to_cents,
    resolve_isbn,
)

import pytest


# --- ISBN normalization -----------------------------------------------------

def test_normalize_isbn_strips_hyphens_and_spaces():
    assert normalize_isbn("0-306-40615-2") == "0306406152"
    assert normalize_isbn("0 306 40615 2") == "0306406152"


def test_normalize_isbn_uppercases_trailing_x():
    assert normalize_isbn("080442957x") == "080442957X"


# --- ISBN-10 checksum --------------------------------------------------------

def test_is_valid_isbn10_accepts_known_good_isbn():
    assert is_valid_isbn10("0306406152") is True


def test_is_valid_isbn10_accepts_x_check_digit():
    assert is_valid_isbn10("080442957X") is True


@pytest.mark.parametrize(
    "bad_isbn10",
    [
        "0306406153",  # wrong check digit
        "030640615",  # too short
        "03064061522",  # too long
        "030640615A",  # non-digit, non-X in a data position
    ],
)
def test_is_valid_isbn10_rejects_bad_input(bad_isbn10):
    assert is_valid_isbn10(bad_isbn10) is False


# --- ISBN-13 checksum --------------------------------------------------------

def test_is_valid_isbn13_accepts_known_good_isbn():
    assert is_valid_isbn13("9780306406157") is True


@pytest.mark.parametrize(
    "bad_isbn13",
    [
        "9780306406158",  # wrong check digit
        "978030640615",  # too short
        "97803064061577",  # too long
    ],
)
def test_is_valid_isbn13_rejects_bad_input(bad_isbn13):
    assert is_valid_isbn13(bad_isbn13) is False


# --- ISBN-10 -> ISBN-13 conversion -------------------------------------------

def test_isbn10_to_isbn13_known_conversion():
    assert isbn10_to_isbn13("0306406152") == "9780306406157"


def test_isbn10_to_isbn13_rejects_bad_checksum():
    with pytest.raises(ValueError):
        isbn10_to_isbn13("0306406153")


# --- resolve_isbn -------------------------------------------------------

def test_resolve_isbn_from_isbn10_returns_derived_isbn13_and_input_isbn10():
    assert resolve_isbn("0-306-40615-2") == ("9780306406157", "0306406152")


def test_resolve_isbn_from_isbn13_returns_isbn13_and_no_isbn10():
    assert resolve_isbn("9780306406157") == ("9780306406157", None)


def test_resolve_isbn_rejects_bad_checksum():
    with pytest.raises(ValueError):
        resolve_isbn("0306406153")


def test_resolve_isbn_rejects_wrong_length():
    with pytest.raises(ValueError):
        resolve_isbn("12345")


# --- price_to_cents -----------------------------------------------------

def test_price_to_cents_brazilian_format_with_symbol():
    assert price_to_cents("R$ 1.234,56") == 123456


def test_price_to_cents_us_format_no_symbol():
    assert price_to_cents("1,234.56") == 123456


def test_price_to_cents_whole_number_no_decimal():
    assert price_to_cents("R$ 45") == 4500


def test_price_to_cents_plain_decimal_string():
    assert price_to_cents("1234.56") == 123456


def test_price_to_cents_uses_decimal_not_float():
    # 19.99 cannot be represented exactly as a binary float; a float-based
    # implementation is prone to landing on 1998 or 2000 instead of 1999.
    assert price_to_cents("19.99") == 1999


def test_price_to_cents_rejects_text_with_no_digits():
    with pytest.raises(ValueError):
        price_to_cents("indisponível")


# --- dataclasses construct and hold values -----------------------------

def test_book_dataclass_round_trips_fields():
    book = Book(
        id=1,
        title="Structure and Interpretation of Computer Programs",
        alt_title=None,
        isbn13="9780262510875",
        isbn10="0262510871",
        author="Abelson & Sussman",
    )
    assert book.active is True
    assert book.created_at is None


def test_listing_dataclass_defaults():
    listing = Listing(id=None, book_id=1, store_slug="mercado_livre", url="https://example.com/p/1")
    assert listing.active is True
    assert listing.store_product_id is None


def test_candidate_dataclass_holds_search_result_fields():
    candidate = Candidate(
        url="https://example.com/p/1",
        store_title="SICP - Capa comum",
        price_cents=12345,
        currency="BRL",
    )
    assert candidate.store_product_id is None


def test_observation_dataclass_holds_status_enum():
    obs = Observation(
        id=None,
        listing_id=1,
        observed_on="2026-07-23",
        observed_at="2026-07-23T03:17:00",
        status=ObservationStatus.OK,
        price_cents=1999,
        currency="BRL",
    )
    assert obs.status == "ok"


def test_fetch_result_is_frozen():
    result = FetchResult(html="<html></html>", status_code=200, final_url="https://x", fetcher="http")
    with pytest.raises(AttributeError):
        result.status_code = 404
