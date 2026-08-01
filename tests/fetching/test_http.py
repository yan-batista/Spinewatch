from pathlib import Path
from unittest.mock import MagicMock

import pytest
from curl_cffi.requests import exceptions as curl_exceptions

from spinewatch.errors import BlockedError
from spinewatch.fetching import http

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mercado_livre"


def make_response(status_code, text="<html></html>", url="https://example.com/final"):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.url = url
    return response


@pytest.fixture(autouse=True)
def no_real_backoff(monkeypatch):
    # Retries happen for real code paths in these tests; don't actually sleep.
    monkeypatch.setattr(http.time, "sleep", lambda *_args: None)


def install_session(monkeypatch, session):
    monkeypatch.setattr(http.requests, "Session", MagicMock(return_value=session))


def test_200_response_returns_fetch_result(monkeypatch):
    session = MagicMock()
    session.get.return_value = make_response(
        200, text="<html>ok</html>", url="https://example.com/x"
    )
    install_session(monkeypatch, session)

    fetcher = http.HttpFetcher(timeout=5.0)
    result = fetcher.fetch("https://example.com/x")

    assert result.html == "<html>ok</html>"
    assert result.status_code == 200
    assert result.final_url == "https://example.com/x"
    assert result.fetcher == "http"
    session.get.assert_called_once_with("https://example.com/x", timeout=5.0)


@pytest.mark.parametrize("status", [403, 503])
def test_403_and_503_raise_blocked_without_retry(monkeypatch, status):
    session = MagicMock()
    session.get.return_value = make_response(status)
    install_session(monkeypatch, session)

    fetcher = http.HttpFetcher()
    with pytest.raises(BlockedError):
        fetcher.fetch("https://example.com/x")

    assert session.get.call_count == 1


def test_500_then_500_raises_blocked_after_one_retry(monkeypatch):
    session = MagicMock()
    session.get.side_effect = [make_response(500), make_response(500)]
    install_session(monkeypatch, session)

    fetcher = http.HttpFetcher()
    with pytest.raises(BlockedError):
        fetcher.fetch("https://example.com/x")

    assert session.get.call_count == 2


def test_500_then_200_succeeds_on_retry(monkeypatch):
    session = MagicMock()
    session.get.side_effect = [
        make_response(500),
        make_response(200, text="ok", url="https://example.com/x"),
    ]
    install_session(monkeypatch, session)

    fetcher = http.HttpFetcher()
    result = fetcher.fetch("https://example.com/x")

    assert result.status_code == 200
    assert result.html == "ok"
    assert session.get.call_count == 2


def test_timeout_on_both_attempts_propagates(monkeypatch):
    session = MagicMock()
    session.get.side_effect = curl_exceptions.Timeout("timed out")
    install_session(monkeypatch, session)

    fetcher = http.HttpFetcher()
    with pytest.raises(curl_exceptions.Timeout):
        fetcher.fetch("https://example.com/x")

    assert session.get.call_count == 2


def test_connection_error_on_both_attempts_propagates(monkeypatch):
    session = MagicMock()
    session.get.side_effect = curl_exceptions.ConnectionError("connection reset")
    install_session(monkeypatch, session)

    fetcher = http.HttpFetcher()
    with pytest.raises(curl_exceptions.ConnectionError):
        fetcher.fetch("https://example.com/x")

    assert session.get.call_count == 2


def test_known_interstitial_marker_raises_blocked_on_200(monkeypatch):
    # Real Mercado Livre bot proof-of-work challenge page: HTTP 200, but the
    # body contains the literal "bot_challenge" marker and must still be
    # treated as blocked.
    challenge_html = (FIXTURES / "blocked_challenge.html").read_text()
    session = MagicMock()
    session.get.return_value = make_response(200, text=challenge_html)
    install_session(monkeypatch, session)

    fetcher = http.HttpFetcher()
    with pytest.raises(BlockedError):
        fetcher.fetch("https://example.com/x")


def test_name_is_http():
    assert http.HttpFetcher.name == "http"


def test_close_closes_session(monkeypatch):
    session = MagicMock()
    install_session(monkeypatch, session)

    fetcher = http.HttpFetcher()
    fetcher.close()

    session.close.assert_called_once()
