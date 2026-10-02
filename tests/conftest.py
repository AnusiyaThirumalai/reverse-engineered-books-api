from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fake_site import FakeSite

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def base_settings() -> Settings:
    """Fast, deterministic settings: no politeness delay or backoff sleeping."""
    return Settings(
        cache_ttl_seconds=300,
        upstream_min_interval_seconds=0,
        retry_backoff_seconds=0,
        max_retries=2,
        rate_limit_requests=1000,
        search_max_pages=5,
        log_level="WARNING",
    )


@pytest.fixture
def site() -> FakeSite:
    return FakeSite()


@pytest.fixture
def make_client(site, base_settings):
    """Factory: ``make_client(rate_limit_requests=3)`` -> TestClient on the fake site."""
    clients: list[TestClient] = []

    def _make(**overrides) -> TestClient:
        app = create_app(replace(base_settings, **overrides), transport=site.transport)
        # raise_server_exceptions=False so the 500 handler can be asserted on
        tc = TestClient(app, raise_server_exceptions=False)
        tc.__enter__()
        clients.append(tc)
        return tc

    yield _make
    for tc in clients:
        tc.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()
