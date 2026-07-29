import sys
from pathlib import Path

import pytest

from book_monitor.errors import BlockedError
from book_monitor.fetching.base import raise_if_interstitial

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_import_does_not_require_playwright_module_scope():
    # Module import must never touch playwright.sync_api — that happens
    # lazily, inside BrowserFetcher.__init__, so this module stays importable
    # on a machine with no Playwright/Chromium installed.
    sys.modules.pop("book_monitor.fetching.browser", None)
    sys.modules.pop("playwright.sync_api", None)

    import book_monitor.fetching.browser  # noqa: F401

    assert "playwright.sync_api" not in sys.modules


def test_name_is_browser():
    from book_monitor.fetching.browser import BrowserFetcher

    assert BrowserFetcher.name == "browser"


def test_raise_if_interstitial_raises_for_ml_marker():
    html = (FIXTURES / "mercado_livre" / "blocked_challenge.html").read_text()
    with pytest.raises(BlockedError):
        raise_if_interstitial(html, "https://example.com/x")


def test_raise_if_interstitial_raises_for_amazon_marker():
    html = (FIXTURES / "amazon_br" / "blocked.html").read_text()
    with pytest.raises(BlockedError):
        raise_if_interstitial(html, "https://example.com/x")


def test_raise_if_interstitial_does_nothing_for_normal_page():
    html = (FIXTURES / "mercado_livre" / "normal.html").read_text()
    raise_if_interstitial(html, "https://example.com/x")  # must not raise
