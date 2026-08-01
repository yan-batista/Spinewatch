from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Mapping, TypeVar

T = TypeVar("T")


def _get(env: Mapping[str, str], name: str, default: T, cast: Callable[[str], T]) -> T:
    raw = env.get(name)
    if not raw:
        return default
    return cast(raw)


def _split_csv(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    db_path: str = "books.db"
    request_delay_min: float = 2.0
    request_delay_max: float = 5.0
    http_timeout: float = 20.0
    browser_timeout: float = 30.0
    max_escalations: int = 25
    fixture_dir: str = "tests/fixtures"
    log_level: str = "INFO"
    cors_origins: tuple[str, ...] = ()
    api_key: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        defaults = cls()
        return cls(
            db_path=_get(env, "SPINEWATCH_DB_PATH", defaults.db_path, str),
            request_delay_min=_get(
                env, "SPINEWATCH_REQUEST_DELAY_MIN", defaults.request_delay_min, float
            ),
            request_delay_max=_get(
                env, "SPINEWATCH_REQUEST_DELAY_MAX", defaults.request_delay_max, float
            ),
            http_timeout=_get(env, "SPINEWATCH_HTTP_TIMEOUT", defaults.http_timeout, float),
            browser_timeout=_get(
                env, "SPINEWATCH_BROWSER_TIMEOUT", defaults.browser_timeout, float
            ),
            max_escalations=_get(
                env, "SPINEWATCH_MAX_ESCALATIONS", defaults.max_escalations, int
            ),
            fixture_dir=_get(env, "SPINEWATCH_FIXTURE_DIR", defaults.fixture_dir, str),
            log_level=_get(env, "SPINEWATCH_LOG_LEVEL", defaults.log_level, str),
            cors_origins=_get(
                env, "SPINEWATCH_CORS_ORIGINS", defaults.cors_origins, _split_csv
            ),
            api_key=_get(env, "SPINEWATCH_API_KEY", defaults.api_key, str),
        )
