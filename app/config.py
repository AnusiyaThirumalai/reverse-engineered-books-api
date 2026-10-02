"""Application configuration.

Tunables come from environment variables (see ``.env.example``). The *target*
website is intentionally NOT configurable: hard-coding it is part of the SSRF
defence (the service can only ever talk to one host).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# --- Fixed target (deliberately not environment-driven) -----------------------
TARGET_BASE_URL = "https://books.toscrape.com"
ALLOWED_HOSTS = frozenset({"books.toscrape.com"})
UPSTREAM_PAGE_SIZE = 20  # the target site renders 20 books per listing page
USER_AGENT = (
    "ReverseEngineeredAPI/1.0 (hiring-assignment demo; polite, rate-limited, "
    "public pages only)"
)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Immutable so it can be shared safely."""

    app_env: str = "development"
    log_level: str = "INFO"
    cache_ttl_seconds: int = 300
    cache_max_entries: int = 512
    request_timeout_seconds: float = 10.0
    max_retries: int = 2  # retries AFTER the first attempt
    retry_backoff_seconds: float = 0.5  # exponential: 0.5s, 1s, 2s ...
    upstream_min_interval_seconds: float = 0.2  # politeness gap between upstream requests
    rate_limit_requests: int = 30  # inbound, per client
    rate_limit_window_seconds: int = 60
    search_max_pages: int = 10  # listing pages scanned per search (20 books/page)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            cache_ttl_seconds=_env_int("CACHE_TTL_SECONDS", 300),
            cache_max_entries=_env_int("CACHE_MAX_ENTRIES", 512),
            request_timeout_seconds=_env_float("REQUEST_TIMEOUT_SECONDS", 10.0),
            max_retries=_env_int("MAX_RETRIES", 2),
            retry_backoff_seconds=_env_float("RETRY_BACKOFF_SECONDS", 0.5),
            upstream_min_interval_seconds=_env_float("UPSTREAM_MIN_INTERVAL_SECONDS", 0.2),
            rate_limit_requests=_env_int("RATE_LIMIT_REQUESTS", 30),
            rate_limit_window_seconds=_env_int("RATE_LIMIT_WINDOW_SECONDS", 60),
            search_max_pages=_env_int("SEARCH_MAX_PAGES", 10),
        )
