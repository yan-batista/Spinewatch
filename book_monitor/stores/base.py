"""The Store contract every adapter implements: parsing only, no HTTP, no DB."""

from __future__ import annotations

from abc import ABC, abstractmethod

from book_monitor.errors import SearchNotSupported
from book_monitor.models import Candidate, ParsedListing


class Store(ABC):
    slug: str
    name: str
    allow_browser_fallback: bool = True
    request_delay: tuple[float, float] = (2.0, 5.0)

    @abstractmethod
    def parse_listing(self, html: str, url: str) -> ParsedListing:
        """Extract price, currency, stock, seller. Raise on failure."""

    def search_url(self, query: str) -> str:
        """Optional. Build this store's search-results URL for a query.

        No HTTP here — same fetch/parse separation as `parse_listing`.
        Default raises SearchNotSupported.
        """
        raise SearchNotSupported(f"{type(self).__name__} does not support search")

    def parse_search_results(self, html: str, query: str) -> list[Candidate]:
        """Optional. Parse a fetched search-results page into candidates.

        Default raises SearchNotSupported.
        """
        raise SearchNotSupported(f"{type(self).__name__} does not support search")

    @abstractmethod
    def matches_url(self, url: str) -> bool:
        """Does this URL belong to this store? Used by `books link`."""

    @abstractmethod
    def normalize_url(self, url: str) -> str:
        """Strip tracking/affiliate/session parameters."""
