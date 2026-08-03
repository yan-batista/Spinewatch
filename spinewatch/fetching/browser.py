"""Browser fetcher: Playwright/Chromium fallback for pages that block plain HTTP.

Playwright is an optional dependency (`pip install -e ".[browser]"`), so the
import must stay inside the constructor — importing this module must never
fail, and must never require Chromium, on a machine with neither installed.
"""

import time

from spinewatch.fetching.base import (
    is_interstitial,
    raise_if_blocked_status,
    raise_if_interstitial,
)
from spinewatch.models import FetchResult

_BLOCKED_RESOURCE_TYPES = {"image", "font", "media", "stylesheet"}

# How long to let a self-clearing challenge page resolve before calling it a
# block. ML's proof-of-work takes ~6s; the rest is headroom for a slow run.
_CHALLENGE_SETTLE_SECONDS = 20.0
_CHALLENGE_POLL_MS = 1000

# Both stores are Brazilian, so an en-US browser is itself an oddity worth not
# advertising.
_LOCALE = "pt-BR"


def _settled_content(page) -> str:
    """Return the page's HTML once it stops being a bot interstitial.

    A challenge page is JavaScript that runs, clears itself, and navigates to
    the real content -- Mercado Livre's takes ~6s. Reading at
    `domcontentloaded` therefore snapshots the challenge itself and reports a
    page that was about to load fine as blocked. Poll until it clears, then
    give up and return the last interstitial so the caller still raises.
    """
    deadline = time.monotonic() + _CHALLENGE_SETTLE_SECONDS
    html = ""
    while True:
        try:
            html = page.content()
        except Exception:  # noqa: BLE001 - mid-navigation; retry on the next tick
            html = html or ""
        if html and not is_interstitial(html):
            return html
        if time.monotonic() >= deadline:
            return html
        page.wait_for_timeout(_CHALLENGE_POLL_MS)


def _undisguised_ua(ua: str) -> str:
    """Strip the "Headless" marker out of Chromium's default user agent.

    Headless Chromium ships a UA that literally reads `HeadlessChrome/...`.
    Derived from the live UA rather than hardcoded so the Chrome version stays
    correct across Playwright upgrades on its own.
    """
    return ua.replace("HeadlessChrome/", "Chrome/")


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
            args=[
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-sandbox",
                # Without this Chromium sets navigator.webdriver = true, which
                # is a one-line "I am a bot" declaration to any detector.
                "--disable-blink-features=AutomationControlled",
            ]
        )
        probe = self._browser.new_context()
        try:
            self._user_agent = _undisguised_ua(
                probe.new_page().evaluate("navigator.userAgent")
            )
        finally:
            probe.close()

    def fetch(self, url: str) -> FetchResult:
        context = self._browser.new_context(
            user_agent=self._user_agent, locale=_LOCALE
        )
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
            html = _settled_content(page)
            final_url = page.url
            status_code = response.status if response is not None else 200
        finally:
            context.close()

        raise_if_blocked_status(status_code, url)
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
