from pathlib import Path

import pytest

from book_monitor.errors import NotFoundError, UnavailableError
from book_monitor.models import ParsedListing
from book_monitor.stores.mercado_livre import MercadoLivreStore

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mercado_livre"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture
def store() -> MercadoLivreStore:
    return MercadoLivreStore()


def test_parse_listing_normal_returns_parsed_listing(store):
    result = store.parse_listing(_read("normal.html"), "https://produto.mercadolivre.com.br/x")

    assert result == ParsedListing(
        price_cents=9490,
        currency="BRL",
        in_stock=True,
        title="Livro Código Limpo | Robert C. Martin | Clean Code",
        seller="Livraria Cultura Oficial",
        raw_price_text="94.90",
    )


def test_parse_listing_unavailable_raises(store):
    with pytest.raises(UnavailableError):
        store.parse_listing(_read("unavailable.html"), "https://produto.mercadolivre.com.br/x")


def test_parse_listing_not_found_raises(store):
    with pytest.raises(NotFoundError):
        store.parse_listing(_read("not_found.html"), "https://produto.mercadolivre.com.br/x")


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://produto.mercadolivre.com.br/MLB-123-foo", True),
        ("https://www.mercadolivre.com.br/foo/up/MLBU123", True),
        ("https://www.amazon.com.br/dp/123", False),
    ],
)
def test_matches_url(store, url, expected):
    assert store.matches_url(url) is expected


def test_normalize_url_strips_query_and_is_idempotent(store):
    url = "https://produto.mercadolivre.com.br/MLB-123-foo?utm_source=foo&tracking_id=bar"
    normalized = store.normalize_url(url)

    assert normalized == "https://produto.mercadolivre.com.br/MLB-123-foo"
    assert store.normalize_url(normalized) == normalized
