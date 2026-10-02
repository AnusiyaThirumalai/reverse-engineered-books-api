import pytest

from app.services.cache import TTLCache
from app.services.rate_limiter import SlidingWindowRateLimiter
from app.services.scraper import WebsiteClient


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_cache_expires_after_ttl():
    clock = Clock()
    cache = TTLCache[str](ttl_seconds=10, clock=clock)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    clock.t = 10.1
    assert cache.get("k") is None
    assert (cache.hits, cache.misses) == (1, 1)


def test_cache_evicts_when_full():
    cache = TTLCache[int](ttl_seconds=100, max_entries=2)
    for i in range(3):
        cache.set(str(i), i)
    assert len(cache) == 2 and cache.get("0") is None and cache.get("2") == 2


def test_rate_limiter_window_slides():
    clock = Clock()
    rl = SlidingWindowRateLimiter(2, 60, clock=clock)
    assert rl.check("a")[0] and rl.check("a")[0]
    allowed, retry_after = rl.check("a")
    assert not allowed and retry_after == pytest.approx(60)
    assert rl.check("b")[0]  # separate client, separate budget
    clock.t = 61
    assert rl.check("a")[0]


@pytest.mark.parametrize(
    "bad", ["https://evil.example.com/x", "http://books.toscrape.com/x", "https://books.toscrape.com.evil.com/x"]
)
def test_client_refuses_other_hosts(bad):
    with pytest.raises(ValueError):
        WebsiteClient.build_url(bad)


def test_client_builds_urls_on_target_host():
    assert WebsiteClient.build_url("/catalogue/page-2.html") == "https://books.toscrape.com/catalogue/page-2.html"
    # protocol-relative tricks stay on the target host
    assert WebsiteClient.build_url("//evil.example.com/x").startswith("https://books.toscrape.com/")
