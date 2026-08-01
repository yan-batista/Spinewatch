"""Mercado Livre store adapter: parses the JSON-LD Product/Offer block that
every Mercado Livre product page embeds (real captures confirm the shape --
see the saved pages under tests/fixtures/mercado_livre/).
"""

from __future__ import annotations

import json
import re
from urllib.parse import quote, urlsplit, urlunsplit

from selectolax.parser import HTMLParser

from spinewatch.errors import NotFoundError, ParseError, UnavailableError
from spinewatch.models import Candidate, ParsedListing, price_to_cents
from spinewatch.stores.base import Store

_HOST_SUFFIXES = ("mercadolivre.com.br", "mercadolibre.com")
_PRODUCT_ID_RE = re.compile(r"MLB-?(\d+)")


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

        try:
            price_cents = price_to_cents(str(price_text))
        except ValueError as exc:
            raise ParseError(f"unparseable price {price_text!r} in JSON-LD offer: {url}") from exc

        return ParsedListing(
            price_cents=price_cents,
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

    def search_url(self, query: str) -> str:
        slug = quote(query.strip().replace(" ", "-"))
        return f"https://lista.mercadolivre.com.br/{slug}"

    def parse_search_results(self, html: str, query: str) -> list[Candidate]:
        tree = HTMLParser(html)
        candidates = []
        for item in tree.css("li.ui-search-layout__item"):
            link = item.css_first("a.ui-search-link")
            title_node = item.css_first("h2.ui-search-item__title")
            if link is None or title_node is None:
                continue
            url = link.attributes.get("href")
            if not url:
                continue

            price_cents = None
            fraction = item.css_first(".andes-money-amount__fraction")
            if fraction is not None:
                cents = item.css_first(".andes-money-amount__cents")
                price_text = f"{fraction.text()}.{cents.text() if cents is not None else '00'}"
                try:
                    price_cents = price_to_cents(price_text)
                except ValueError:
                    price_cents = None

            product_id_match = _PRODUCT_ID_RE.search(url)
            candidates.append(
                Candidate(
                    url=url,
                    store_title=title_node.text().strip(),
                    price_cents=price_cents,
                    currency="BRL",
                    store_product_id=product_id_match.group(1) if product_id_match else None,
                )
            )
        return candidates


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
