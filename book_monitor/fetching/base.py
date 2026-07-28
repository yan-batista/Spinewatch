"""The Fetcher contract shared by every transport (plain HTTP, browser fallback, ...)."""

from typing import Protocol

from book_monitor.models import FetchResult


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchResult: ...

    def close(self) -> None: ...
