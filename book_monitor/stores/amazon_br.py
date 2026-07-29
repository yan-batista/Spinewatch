"""Amazon Brazil store adapter: no JSON-LD (verified against a real capture),
so this parses the rendered CSS structure directly.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from selectolax.parser import HTMLParser

from book_monitor.errors import NotFoundError, ParseError, UnavailableError
from book_monitor.models import ParsedListing, price_to_cents
from book_monitor.stores.base import Store

_HOST_SUFFIX = "amazon.com.br"
_NOT_FOUND_MARKER = "Não foi possível encontrar esta página"
_UNAVAILABLE_MARKERS = ("unavailable", "não está disponível")


class AmazonBrStore(Store):
    slug = "amazon_br"
    name = "Amazon.com.br"

    def parse_listing(self, html: str, url: str) -> ParsedListing:
        tree = HTMLParser(html)
        title_node = tree.css_first("#productTitle")

        if title_node is None:
            if _NOT_FOUND_MARKER in html:
                raise NotFoundError(f"listing not found: {url}")
            raise ParseError(f"no #productTitle found: {url}")

        availability_node = tree.css_first("#availability span")
        availability_text = availability_node.text().strip() if availability_node else ""
        if any(marker in availability_text.lower() for marker in _UNAVAILABLE_MARKERS):
            raise UnavailableError(f"listing unavailable: {url}")

        price_text = _extract_price_text(tree)
        if price_text is None:
            raise ParseError(f"no price found in #corePriceDisplay_desktop_feature_div: {url}")

        try:
            price_cents = price_to_cents(price_text)
        except ValueError as exc:
            raise ParseError(f"unparseable price {price_text!r}: {url}") from exc

        return ParsedListing(
            price_cents=price_cents,
            # amazon.com.br only ever sells in BRL; there's no machine-readable
            # currency field on the page to read this from.
            currency="BRL",
            in_stock=True,
            title=title_node.text().strip(),
            seller=None,
            raw_price_text=price_text,
        )

    def matches_url(self, url: str) -> bool:
        host = urlsplit(url).hostname or ""
        return host == _HOST_SUFFIX or host.endswith(f".{_HOST_SUFFIX}")

    def normalize_url(self, url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _extract_price_text(tree: HTMLParser) -> str | None:
    """First populated price text inside `#corePriceDisplay_desktop_feature_div`.

    Amazon normally renders the price into a `.a-offscreen` accessibility
    span, but this fixture's pricing experiment bucket leaves that span
    blank and only fills the visible `.a-price-whole` / `.a-price-fraction`
    spans server-side — so fall back to reconstructing from those.
    """
    container = tree.css_first("#corePriceDisplay_desktop_feature_div")
    if container is None:
        return None
    price = container.css_first(".a-price")
    if price is None:
        return None

    offscreen = price.css_first(".a-offscreen")
    if offscreen is not None:
        text = offscreen.text().strip()
        if text:
            return text

    whole = price.css_first(".a-price-whole")
    fraction = price.css_first(".a-price-fraction")
    if whole is not None and fraction is not None:
        return f"{whole.text()}{fraction.text()}"
    return None
