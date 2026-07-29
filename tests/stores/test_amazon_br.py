from pathlib import Path

import pytest

from book_monitor.errors import BlockedError, NotFoundError, UnavailableError
from book_monitor.fetching.base import raise_if_interstitial
from book_monitor.models import Candidate
from book_monitor.stores.amazon_br import AmazonBrStore

FIXTURES = Path(__file__).parent.parent / "fixtures" / "amazon_br"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def store() -> AmazonBrStore:
    return AmazonBrStore()


def test_parse_listing_normal_returns_parsed_listing(store):
    result = store.parse_listing(_read("normal.html"), "https://www.amazon.com.br/dp/0132350882")

    assert result.price_cents == 25121
    assert result.currency == "BRL"
    assert result.in_stock is True
    assert result.title == "Clean Code: A Handbook of Agile Software Craftsmanship"


def test_parse_listing_unavailable_raises(store):
    with pytest.raises(UnavailableError):
        store.parse_listing(_read("unavailable.html"), "https://www.amazon.com.br/dp/0132350884")


def test_parse_listing_not_found_raises(store):
    with pytest.raises(NotFoundError):
        store.parse_listing(_read("not_found.html"), "https://www.amazon.com.br/dp/doesnotexist")


def test_blocked_fixture_raises_via_shared_interstitial_helper():
    with pytest.raises(BlockedError):
        raise_if_interstitial(_read("blocked.html"), "https://www.amazon.com.br/dp/0132350882")


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "https://www.amazon.com.br/Clean-Code-Handbook-Software-Craftsmanship/dp/0132350882",
            True,
        ),
        ("https://amazon.com.br/dp/0132350882", True),
        ("https://www.amazon.com/dp/0132350882", False),
        ("https://produto.mercadolivre.com.br/foo", False),
    ],
)
def test_matches_url(store, url, expected):
    assert store.matches_url(url) is expected


def test_normalize_url_strips_query_and_is_idempotent(store):
    url = (
        "https://www.amazon.com.br/Clean-Code-Handbook-Software-Craftsmanship/dp/0132350882"
        "?tag=someaffiliate-20&ref=sr_1_1&qid=123"
    )
    normalized = store.normalize_url(url)

    assert normalized == (
        "https://www.amazon.com.br/Clean-Code-Handbook-Software-Craftsmanship/dp/0132350882"
    )
    assert store.normalize_url(normalized) == normalized


def test_search_url_builds_expected_shape(store):
    assert store.search_url("clean code robert martin") == (
        "https://www.amazon.com.br/s?k=clean+code+robert+martin"
    )


def test_parse_search_results_returns_expected_candidates(store):
    candidates = store.parse_search_results(
        _read("search_results.html"), "clean code robert martin"
    )

    assert [c.store_product_id for c in candidates] == [
        "8576082675",
        "0135398576",
        "0132350882",
    ]
    assert [c.price_cents for c in candidates] == [7691, 32577, 25121]
    assert [c.url for c in candidates] == [
        "https://www.amazon.com.br/dp/8576082675",
        "https://www.amazon.com.br/dp/0135398576",
        "https://www.amazon.com.br/dp/0132350882",
    ]
    assert candidates[0].store_title == "Código limpo: habilidades práticas do Agile Software"
    assert candidates[1].store_title == "Clean Code: A Handbook of Agile Software Craftsmanship"
    assert all(c.currency == "BRL" for c in candidates)
