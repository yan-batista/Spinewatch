import sys
from pathlib import Path

import pytest

from spinewatch.errors import BlockedError
from spinewatch.fetching.base import raise_if_interstitial

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_import_does_not_require_playwright_module_scope():
    # Module import must never touch playwright.sync_api — that happens
    # lazily, inside BrowserFetcher.__init__, so this module stays importable
    # on a machine with no Playwright/Chromium installed.
    sys.modules.pop("spinewatch.fetching.browser", None)
    sys.modules.pop("playwright.sync_api", None)

    import spinewatch.fetching.browser  # noqa: F401

    assert "playwright.sync_api" not in sys.modules


def test_name_is_browser():
    from spinewatch.fetching.browser import BrowserFetcher

    assert BrowserFetcher.name == "browser"


def test_raise_if_interstitial_raises_for_ml_marker():
    html = (FIXTURES / "mercado_livre" / "blocked_challenge.html").read_text()
    with pytest.raises(BlockedError):
        raise_if_interstitial(html, "https://example.com/x")


def test_raise_if_interstitial_raises_for_ml_account_verification():
    # Real capture: once an IP is rate-flagged, ML stops serving the
    # proof-of-work page and 302s product URLs to /gz/account-verification --
    # HTTP 200, no "bot_challenge" marker anywhere. Must be blocked, not
    # handed to the store parser as a shape change.
    html = (FIXTURES / "mercado_livre" / "blocked_account_verification.html").read_text()
    assert "bot_challenge" not in html
    with pytest.raises(BlockedError):
        raise_if_interstitial(html, "https://example.com/x")


def test_raise_if_interstitial_raises_for_ml_captcha_wall():
    # Real capture: the proof-of-work page does not always resolve into the
    # product page -- on a degraded IP it escalates to /captcha/wall, which
    # drops the PoW markup entirely. Third distinct ML block page, third
    # disjoint marker.
    html = (FIXTURES / "mercado_livre" / "blocked_captcha_wall.html").read_text()
    assert "bot_challenge" not in html
    assert "suspicious-traffic-frontend" not in html
    with pytest.raises(BlockedError):
        raise_if_interstitial(html, "https://example.com/x")


def test_raise_if_interstitial_raises_for_amazon_marker():
    html = (FIXTURES / "amazon_br" / "blocked.html").read_text()
    with pytest.raises(BlockedError):
        raise_if_interstitial(html, "https://example.com/x")


def test_raise_if_interstitial_does_nothing_for_normal_page():
    html = (FIXTURES / "mercado_livre" / "normal.html").read_text()
    raise_if_interstitial(html, "https://example.com/x")  # must not raise


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status


class _FakePage:
    def __init__(self, response: "_FakeResponse") -> None:
        self._response = response
        self.url = "https://example.com/x"

    def route(self, pattern, handler) -> None:
        pass

    def goto(self, url, wait_until=None, timeout=None) -> "_FakeResponse":
        return self._response

    def content(self) -> str:
        return "<html>bot wall, no recognizable product markup</html>"

    def wait_for_timeout(self, ms) -> None:
        pass


class _FakeContext:
    def __init__(self, response: "_FakeResponse") -> None:
        self._response = response

    def new_page(self) -> "_FakePage":
        return _FakePage(self._response)

    def close(self) -> None:
        pass


class _FakeBrowser:
    def __init__(self, response: "_FakeResponse") -> None:
        self._response = response

    def new_context(self, **kwargs) -> "_FakeContext":
        return _FakeContext(self._response)


@pytest.mark.parametrize("status", [403, 503])
def test_fetch_raises_blocked_error_for_blocked_status(status):
    from spinewatch.fetching.browser import BrowserFetcher

    fetcher = object.__new__(BrowserFetcher)
    fetcher.timeout = 30.0
    fetcher._user_agent = "test-agent"
    fetcher._browser = _FakeBrowser(_FakeResponse(status))

    with pytest.raises(BlockedError):
        fetcher.fetch("https://example.com/x")


# --- self-clearing challenge pages -----------------------------------------

class _ChallengePage:
    """Serves a bot interstitial for the first `rounds` reads, then real HTML.

    Mirrors Mercado Livre: the challenge is JS that clears itself after a few
    seconds and navigates on to the product page.
    """

    def __init__(self, rounds: int, final: str = "<html>real product</html>") -> None:
        self.rounds = rounds
        self.final = final
        self.reads = 0
        self.waits = 0

    def content(self) -> str:
        self.reads += 1
        if self.reads <= self.rounds:
            return "<html>bot_challenge in progress</html>"
        return self.final

    def wait_for_timeout(self, ms) -> None:
        self.waits += 1


def test_settled_content_waits_for_a_challenge_to_clear():
    # Reading at domcontentloaded would snapshot the challenge and report a
    # page that was about to load fine as blocked.
    from spinewatch.fetching.browser import _settled_content

    page = _ChallengePage(rounds=3)
    assert _settled_content(page) == "<html>real product</html>"
    assert page.waits == 3  # polled rather than giving up on the first read


def test_settled_content_returns_the_interstitial_when_it_never_clears(monkeypatch):
    # A challenge that never resolves must still surface as blocked, not hang
    # or masquerade as content.
    from spinewatch.fetching import browser

    monkeypatch.setattr(browser, "_CHALLENGE_SETTLE_SECONDS", 0.0)
    page = _ChallengePage(rounds=10_000)

    assert "bot_challenge" in browser._settled_content(page)
    with pytest.raises(BlockedError):
        raise_if_interstitial(browser._settled_content(page), "https://example.com/x")
