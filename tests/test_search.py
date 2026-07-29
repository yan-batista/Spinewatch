import pytest

from book_monitor.errors import SearchNotSupported
from book_monitor.models import Book, Candidate, FetchResult
from book_monitor.search import find_candidates


class FakeFetcher:
    def __init__(self, name: str = "fake"):
        self.name = name
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        return FetchResult(html=f"<html for {url}>", status_code=200, final_url=url, fetcher=self.name)

    def close(self) -> None:
        pass


class FakeSearchStore:
    """Driven by a dict of query -> list[Candidate]; missing query -> []."""

    def __init__(self):
        self.candidates_by_query: dict[str, list[Candidate]] = {}
        self.search_url_calls: list[str] = []
        self.parse_calls: list[tuple[str, str]] = []
        self.raise_on_search_url: Exception | None = None

    def search_url(self, query: str) -> str:
        self.search_url_calls.append(query)
        if self.raise_on_search_url is not None:
            raise self.raise_on_search_url
        return f"https://example.com/search?q={query}"

    def parse_search_results(self, html: str, query: str) -> list[Candidate]:
        self.parse_calls.append((html, query))
        return self.candidates_by_query.get(query, [])


def _book(**overrides) -> Book:
    defaults = dict(
        id=1, title="Clean Code", alt_title="Codigo Limpo", isbn13="9780132350884",
        isbn10=None, author="Robert Martin",
    )
    defaults.update(overrides)
    return Book(**defaults)


def _candidate(url: str = "https://x/1") -> Candidate:
    return Candidate(url=url, store_title="Some Title", price_cents=1000, currency="BRL", store_product_id="1")


def test_isbn13_hit_stops_before_title_and_alt_title():
    store = FakeSearchStore()
    candidate = _candidate()
    store.candidates_by_query["9780132350884"] = [candidate]
    book = _book()
    fetcher = FakeFetcher()

    candidates, query_used = find_candidates(fetcher, store, book)

    assert candidates == [candidate]
    assert query_used == "9780132350884"
    assert store.search_url_calls == ["9780132350884"]
    assert len(fetcher.calls) == 1


def test_falls_through_to_title_when_isbn13_yields_empty():
    store = FakeSearchStore()
    candidate = _candidate()
    store.candidates_by_query["9780132350884"] = []
    store.candidates_by_query["Clean Code"] = [candidate]
    book = _book()
    fetcher = FakeFetcher()

    candidates, query_used = find_candidates(fetcher, store, book)

    assert candidates == [candidate]
    assert query_used == "Clean Code"
    assert store.search_url_calls == ["9780132350884", "Clean Code"]


def test_falls_through_to_title_when_isbn13_is_none():
    store = FakeSearchStore()
    candidate = _candidate()
    store.candidates_by_query["Clean Code"] = [candidate]
    book = _book(isbn13=None)
    fetcher = FakeFetcher()

    candidates, query_used = find_candidates(fetcher, store, book)

    assert candidates == [candidate]
    assert query_used == "Clean Code"
    assert store.search_url_calls == ["Clean Code"]


def test_falls_through_to_alt_title_when_isbn13_and_title_empty():
    store = FakeSearchStore()
    candidate = _candidate()
    store.candidates_by_query["9780132350884"] = []
    store.candidates_by_query["Clean Code"] = []
    store.candidates_by_query["Codigo Limpo"] = [candidate]
    book = _book()
    fetcher = FakeFetcher()

    candidates, query_used = find_candidates(fetcher, store, book)

    assert candidates == [candidate]
    assert query_used == "Codigo Limpo"
    assert store.search_url_calls == ["9780132350884", "Clean Code", "Codigo Limpo"]


def test_all_empty_returns_empty_list_and_empty_query_no_exception():
    store = FakeSearchStore()
    book = _book()
    fetcher = FakeFetcher()

    candidates, query_used = find_candidates(fetcher, store, book)

    assert candidates == []
    assert query_used == ""
    assert store.search_url_calls == ["9780132350884", "Clean Code", "Codigo Limpo"]


def test_all_absent_returns_empty_list_and_empty_query():
    store = FakeSearchStore()
    book = _book(isbn13=None, title=None, alt_title=None)
    fetcher = FakeFetcher()

    candidates, query_used = find_candidates(fetcher, store, book)

    assert candidates == []
    assert query_used == ""
    assert store.search_url_calls == []
    assert fetcher.calls == []


def test_search_not_supported_propagates():
    store = FakeSearchStore()
    store.raise_on_search_url = SearchNotSupported("nope")
    book = _book()
    fetcher = FakeFetcher()

    with pytest.raises(SearchNotSupported):
        find_candidates(fetcher, store, book)
