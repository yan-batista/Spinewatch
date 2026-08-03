"""The Fetcher contract shared by every transport (plain HTTP, browser fallback, ...)."""

from typing import Protocol

from spinewatch.errors import BlockedError
from spinewatch.models import FetchResult

# A 200 response can still be a bot interstitial (e.g. Mercado Livre's
# proof-of-work challenge page, or Amazon's CAPTCHA form). Detected by a
# literal substring, not a per-store thing — any store-specific parsing
# belongs in stores/, not here.
#
# Mercado Livre has *three* of these, with pairwise-disjoint markers, and it
# escalates through them as an IP's reputation degrades:
#
#   1. the proof-of-work page          -> "bot_challenge"
#   2. the captcha wall (/captcha/wall) -> "captcha/wall"
#   3. the /gz/account-verification gate -> "suspicious-traffic-frontend"
#
# All three serve HTTP 200, and (2) and (3) carry none of (1)'s PoW markup.
# Miss one and it sails through to the store parser, which reports the bogus
# "no JSON-LD Product block found" ParseError -- "the page changed shape" --
# for what is plainly a block.
_INTERSTITIAL_MARKERS = (
    "bot_challenge",
    "captcha/wall",
    "suspicious-traffic-frontend",
    "validateCaptcha",
)

# Status codes that mean "the store is fighting back", not "the page changed
# shape". Shared by every fetcher (HttpFetcher, BrowserFetcher, ...) so a
# blocked escalation attempt is recorded the same way a blocked plain-HTTP
# attempt is.
BLOCKED_STATUSES = {403, 503}


def is_interstitial(html: str) -> bool:
    """Does `html` match a known bot-interstitial marker?"""
    return any(marker in html for marker in _INTERSTITIAL_MARKERS)


def raise_if_interstitial(html: str, url: str) -> None:
    """Raise BlockedError if `html` matches a known bot-interstitial marker."""
    if is_interstitial(html):
        raise BlockedError(f"blocked by known interstitial fetching {url}")


def raise_if_blocked_status(status_code: int, url: str) -> None:
    """Raise BlockedError if `status_code` is a known blocked status (403/503)."""
    if status_code in BLOCKED_STATUSES:
        raise BlockedError(f"blocked with status {status_code} fetching {url}")


class Fetcher(Protocol):
    name: str

    def fetch(self, url: str) -> FetchResult: ...

    def close(self) -> None: ...
