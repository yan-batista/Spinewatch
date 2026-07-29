"""Browser fetcher: Playwright/Chromium fallback for pages that block plain HTTP.

Playwright is an optional dependency (`pip install -e ".[browser]"`), so the
import must stay inside the constructor — importing this module must never
fail, and must never require Chromium, on a machine with neither installed.
"""

from book_monitor.fetching.base import raise_if_interstitial
from book_monitor.models import FetchResult

_BLOCKED_RESOURCE_TYPES = {"image", "font", "media", "stylesheet"}


class BrowserFetcher:
    """Fetches a URL with a real (headless) Chromium via Playwright.

    One browser per instance, reused across `fetch()` calls; each call gets
    its own context/page so cookies/storage never leak between fetches.
    """

    name = "browser"

    def __init__(self, *, timeout: float = 30.0) -> None:
        from playwright.sync_api import sync_playwright

        self.timeout = timeout
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            args=["--disable-dev-shm-usage", "--disable-gpu", "--no-sandbox"]
        )

    def fetch(self, url: str) -> FetchResult:
        context = self._browser.new_context()
        try:
            page = context.new_page()

            def _handle_route(route):
                if route.request.resource_type in _BLOCKED_RESOURCE_TYPES:
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", _handle_route)

            response = page.goto(
                url, wait_until="domcontentloaded", timeout=self.timeout * 1000
            )
            html = page.content()
            final_url = page.url
            status_code = response.status if response is not None else 200
        finally:
            context.close()

        raise_if_interstitial(html, url)

        return FetchResult(
            html=html,
            status_code=status_code,
            final_url=final_url,
            fetcher="browser",
        )

    def close(self) -> None:
        self._browser.close()
        self._playwright.stop()
