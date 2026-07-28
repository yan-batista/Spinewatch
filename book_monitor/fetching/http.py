"""Plain HTTP fetcher: curl_cffi with Chrome impersonation, one retry on 5xx/timeout."""

import time

from curl_cffi import requests
from curl_cffi.requests import exceptions as curl_exceptions

from book_monitor.errors import BlockedError
from book_monitor.models import FetchResult

_BLOCKED_STATUSES = {403, 503}
_RETRYABLE_EXCEPTIONS = (curl_exceptions.Timeout, curl_exceptions.ConnectionError)
_RETRY_BACKOFF_SECONDS = 1.0
_MAX_ATTEMPTS = 2  # first try + one retry


class HttpFetcher:
    """Fetches a URL over plain HTTP. 403/503 are a clean "blocked" signal (no
    retry); a 5xx or a timeout/connection error gets one retry before giving up.
    """

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self._session = requests.Session(impersonate="chrome")

    def fetch(self, url: str) -> FetchResult:
        response = None
        for attempt in range(_MAX_ATTEMPTS):
            is_last_attempt = attempt == _MAX_ATTEMPTS - 1
            try:
                response = self._session.get(url, timeout=self.timeout)
            except _RETRYABLE_EXCEPTIONS:
                if is_last_attempt:
                    raise
                time.sleep(_RETRY_BACKOFF_SECONDS)
                continue

            if response.status_code in _BLOCKED_STATUSES:
                raise BlockedError(f"blocked with status {response.status_code} fetching {url}")
            if response.status_code >= 500:
                if is_last_attempt:
                    raise BlockedError(
                        f"blocked with status {response.status_code} fetching {url}"
                    )
                time.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            break

        return FetchResult(
            html=response.text,
            status_code=response.status_code,
            final_url=response.url,
            fetcher="http",
        )

    def close(self) -> None:
        self._session.close()
