class StoreError(Exception):
    """Base class for errors raised by fetchers and store adapters."""


class BlockedError(StoreError):
    """The page was withheld: CAPTCHA, 403/503, or a known bot interstitial."""


class NotFoundError(StoreError):
    """404, or a page that says the listing is gone."""


class UnavailableError(StoreError):
    """The page parsed correctly but the product has no purchasable offer."""


class ParseError(StoreError):
    """The page fetched and was not blocked, but the price could not be extracted."""


class SearchNotSupported(StoreError):
    """This store adapter has no search implementation."""
