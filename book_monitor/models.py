from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class ObservationStatus(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    PARSE_ERROR = "parse_error"
    ERROR = "error"


@dataclass
class Book:
    id: int | None
    title: str | None
    alt_title: str | None
    isbn13: str | None
    isbn10: str | None
    author: str | None
    active: bool = True
    created_at: str | None = None


@dataclass
class Listing:
    id: int | None
    book_id: int
    store_slug: str
    url: str
    store_product_id: str | None = None
    store_title: str | None = None
    active: bool = True
    created_at: str | None = None


@dataclass
class Candidate:
    url: str
    store_title: str | None
    price_cents: int | None
    currency: str | None
    store_product_id: str | None = None


@dataclass
class Observation:
    id: int | None
    listing_id: int
    observed_on: str
    observed_at: str
    status: ObservationStatus
    price_cents: int | None = None
    currency: str | None = None
    in_stock: bool | None = None
    seller: str | None = None
    fetcher: str | None = None
    raw_price_text: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class FetchResult:
    html: str
    status_code: int
    final_url: str
    fetcher: str


@dataclass(frozen=True)
class ParsedListing:
    """What a store's `parse_listing` extracted from one page fetch.

    Distinct from `Listing` (the durable book<->store link, keyed to a
    `book_id`) — this is just today's parse result, with no persistence
    identity of its own.
    """

    price_cents: int
    currency: str
    in_stock: bool
    title: str | None = None
    seller: str | None = None
    raw_price_text: str | None = None


# --- ISBN normalization and checksums ---------------------------------------

_ISBN_STRIP_RE = re.compile(r"[^0-9Xx]")


def normalize_isbn(raw: str) -> str:
    """Strip hyphens/spaces and uppercase a trailing ISBN-10 check digit."""
    return _ISBN_STRIP_RE.sub("", raw).upper()


def is_valid_isbn10(isbn10: str) -> bool:
    if len(isbn10) != 10:
        return False
    digits = isbn10[:9]
    if not digits.isdigit():
        return False
    total = sum((10 - i) * int(ch) for i, ch in enumerate(digits))
    check = isbn10[9]
    if check == "X":
        total += 10
    elif check.isdigit():
        total += int(check)
    else:
        return False
    return total % 11 == 0


def is_valid_isbn13(isbn13: str) -> bool:
    if len(isbn13) != 13 or not isbn13.isdigit():
        return False
    total = sum(
        (int(ch) if i % 2 == 0 else int(ch) * 3) for i, ch in enumerate(isbn13)
    )
    return total % 10 == 0


def isbn10_to_isbn13(isbn10: str) -> str:
    if not is_valid_isbn10(isbn10):
        raise ValueError(f"invalid ISBN-10 checksum: {isbn10!r}")
    core = "978" + isbn10[:9]
    total = sum((int(ch) if i % 2 == 0 else int(ch) * 3) for i, ch in enumerate(core))
    check_digit = (10 - (total % 10)) % 10
    return core + str(check_digit)


# --- Price parsing -----------------------------------------------------------

_PRICE_KEEP_RE = re.compile(r"[^\d.,]")
_SEPARATOR_RE = re.compile(r"[.,]")


def price_to_cents(text: str) -> int:
    """Parse a store-displayed or JSON-LD price string into integer cents.

    Handles both Brazilian ("R$ 1.234,56") and US/JSON-LD ("1,234.56" or
    "1234.56") formats by treating the *last* comma-or-period as the decimal
    separator only when it is followed by exactly one or two digits;
    otherwise every separator is treated as a thousands grouping. Always
    goes through Decimal, never float (NFR-8).
    """
    cleaned = _PRICE_KEEP_RE.sub("", text)
    if not cleaned:
        raise ValueError(f"no digits found in price text: {text!r}")

    separators = list(_SEPARATOR_RE.finditer(cleaned))
    if not separators:
        decimal_str = cleaned
    else:
        last = separators[-1]
        trailing = cleaned[last.end():]
        if len(trailing) in (1, 2) and trailing.isdigit():
            integer_part = _SEPARATOR_RE.sub("", cleaned[: last.start()]) or "0"
            decimal_str = f"{integer_part}.{trailing.ljust(2, '0')}"
        else:
            decimal_str = _SEPARATOR_RE.sub("", cleaned)

    cents = (Decimal(decimal_str) * 100).to_integral_value()
    return int(cents)
