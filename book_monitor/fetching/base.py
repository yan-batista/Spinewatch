"""The Fetcher contract shared by every transport (plain HTTP, browser fallback, ...)."""

from typing import Protocol

from book_monitor.errors import BlockedError
from book_monitor.models import FetchResult

# A 200 response can still be a bot interstitial (e.g. Mercado Livre's
# proof-of-work challenge page, or Amazon's CAPTCHA form). Detected by a
# literal substring, not a per-store thing — any store-specific parsing
# belongs in stores/, not here.
_INTERSTITIAL_MARKERS = ("bot_challenge", "validateCaptcha")


def raise_if_interstitial(html: str, url: str) -> None:
    """Raise BlockedError if `html` matches a known bot-interstitial marker."""
    if any(marker in html for marker in _INTERSTITIAL_MARKERS):
        raise BlockedError(f"blocked by known interstitial fetching {url}")


class Fetcher(Protocol):
    name: str

    def fetch(self, url: str) -> FetchResult: ...

    def close(self) -> None: ...
