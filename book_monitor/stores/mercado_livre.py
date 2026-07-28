"""Mercado Livre store adapter: parses the JSON-LD Product/Offer block that
every Mercado Livre product page embeds (real captures confirm the shape;
see docs/superpowers/plans/2026-07-28-phase3-fetching-store-contract.md).
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit, urlunsplit

from selectolax.parser import HTMLParser

from book_monitor.errors import NotFoundError, ParseError, UnavailableError
from book_monitor.models import ParsedListing, price_to_cents
from book_monitor.stores.base import Store

_HOST_SUFFIXES = ("mercadolivre.com.br", "mercadolibre.com")


class MercadoLivreStore(Store):
    slug = "mercado_livre"
    name = "Mercado Livre"

    def parse_listing(self, html: str, url: str) -> ParsedListing:
        tree = HTMLParser(html)
        product = _find_product_ld(tree)
        if product is None:
            if tree.css_first(".ui-search-not-found") is not None:
                raise NotFoundError(f"listing not found: {url}")
            raise ParseError(f"no JSON-LD Product block found: {url}")

        offers = product.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}

        availability = offers.get("availability") or ""
        if "OutOfStock" in availability:
            raise UnavailableError(f"listing out of stock: {url}")

        price_text = offers.get("price")
        currency = offers.get("priceCurrency")
        if price_text is None or not currency:
            raise ParseError(f"no price/currency in JSON-LD offer: {url}")

        seller = offers.get("seller")
        seller_name = seller.get("name") if isinstance(seller, dict) else None

        return ParsedListing(
            price_cents=price_to_cents(str(price_text)),
            currency=currency,
            in_stock="InStock" in availability,
            title=product.get("name"),
            seller=seller_name,
            raw_price_text=str(price_text),
        )

    def matches_url(self, url: str) -> bool:
        host = urlsplit(url).hostname or ""
        return any(
            host == suffix or host.endswith(f".{suffix}") for suffix in _HOST_SUFFIXES
        )

    def normalize_url(self, url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _find_product_ld(tree: HTMLParser) -> dict | None:
    """Return the first JSON-LD block whose `@type` is `Product`, or None."""
    for node in tree.css('script[type="application/ld+json"]'):
        text = node.text()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        for candidate in data if isinstance(data, list) else [data]:
            if isinstance(candidate, dict) and candidate.get("@type") == "Product":
                return candidate
    return None
