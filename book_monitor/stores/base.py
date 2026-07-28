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

    def search(self, query: str) -> list[Candidate]:
        """Optional. Default raises SearchNotSupported."""
        raise SearchNotSupported(f"{type(self).__name__} does not support search")

    @abstractmethod
    def matches_url(self, url: str) -> bool:
        """Does this URL belong to this store? Used by `books link`."""

    @abstractmethod
    def normalize_url(self, url: str) -> str:
        """Strip tracking/affiliate/session parameters."""
