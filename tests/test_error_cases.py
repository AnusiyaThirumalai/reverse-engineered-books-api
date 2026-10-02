import pytest

BAD_REQUESTS = [
    ("/api/v1/search", {}),                       # missing q
    ("/api/v1/search", {"q": ""}),                # empty
    ("/api/v1/search", {"q": "   "}),             # blank
    ("/api/v1/search", {"q": "x" * 101}),         # too long
    ("/api/v1/search", {"q": "x", "limit": 0}),
    ("/api/v1/search", {"q": "x", "limit": 101}),
    ("/api/v1/search", {"q": "x", "category": "Bad Category!"}),
    ("/api/v1/items", {"limit": 0}),
    ("/api/v1/items", {"limit": -5}),
    ("/api/v1/items", {"limit": 100000}),
    ("/api/v1/items", {"limit": "abc"}),
    ("/api/v1/items", {"page": 0}),
    ("/api/v1/items", {"category": "../../etc/passwd"}),
]


@pytest.mark.parametrize("path,params", BAD_REQUESTS)
def test_invalid_input_returns_400(client, site, path, params):
    r = client.get(path, params=params)
    assert r.status_code == 400
    body = r.json()
    assert set(body) == {"error", "message", "status_code"}
    assert body["error"] == "bad_request" and body["status_code"] == 400
    assert site.calls == []  # rejected before any upstream traffic


@pytest.mark.parametrize("bad_id", ["bad id", "no_digits_", "nounderscore", "x" * 200 + "_1", "a;b_1"])
def test_invalid_item_id_returns_400(client, site, bad_id):
    assert client.get(f"/api/v1/items/{bad_id}").status_code == 400
    assert site.calls == []


def test_path_traversal_in_item_id_never_reaches_upstream(client, site):
    # An encoded slash is decoded before routing, so it never matches the item
    # route at all: JSON 404 from the router, and zero upstream traffic.
    r = client.get("/api/v1/items/..%2F..%2Fetc%2Fpasswd_1")
    assert r.status_code in (400, 404) and r.json()["status_code"] == r.status_code
    assert site.calls == []


def test_unknown_route_and_method_are_json(client):
    r = client.get("/nope")
    assert r.status_code == 404 and r.json()["error"] == "not_found"
    r = client.post("/health")
    assert r.status_code == 405 and r.json()["error"] == "method_not_allowed"


# ---- target website failures ------------------------------------------------

ITEM = "/api/v1/items/a-light-in-the-attic_1000"


def test_timeout_is_retried_then_503(client, site):
    site.fail_mode = "timeout"
    r = client.get(ITEM)
    assert r.status_code == 503 and r.json()["error"] == "upstream_unavailable"
    assert len(site.calls) == 3  # 1 attempt + 2 retries, no more


def test_connection_error_503(client, site):
    site.fail_mode = "connect"
    assert client.get(ITEM).status_code == 503


def test_upstream_500_is_retried_then_502(client, site):
    site.fail_mode = "500"
    r = client.get(ITEM)
    assert r.status_code == 502 and r.json()["error"] == "upstream_bad_response"
    assert len(site.calls) == 3


def test_upstream_503_maps_to_503(client, site):
    site.fail_mode = "503"
    assert client.get(ITEM).status_code == 503


def test_upstream_403_not_retried_and_not_bypassed(client, site):
    site.fail_mode = "403"
    r = client.get(ITEM)
    assert r.status_code == 502
    assert len(site.calls) == 1


def test_transient_failure_recovers(client, site):
    site.fail_mode, site.fail_first = "503", 1
    r = client.get(ITEM)
    assert r.status_code == 200
    assert len(site.calls) == 2


def test_malformed_html_item_502(client, site):
    site.fail_mode = "malformed"
    r = client.get(ITEM)
    assert r.status_code == 502 and r.json()["error"] == "upstream_parse_error"


def test_malformed_html_listing_502(client, site):
    site.fail_mode = "malformed"
    assert client.get("/api/v1/items").status_code == 502
    assert client.get("/api/v1/search", params={"q": "x"}).status_code == 502


@pytest.mark.parametrize("mode", ["empty", "text"])
def test_empty_or_non_html_502(client, site, mode):
    site.fail_mode = mode
    assert client.get(ITEM).status_code == 502


def test_unexpected_error_is_500_without_leaking_details(client, monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("secret internal detail /etc/passwd")

    monkeypatch.setattr(client.app.state.catalog, "get_book", boom)
    r = client.get(ITEM)
    assert r.status_code == 500
    assert r.json() == {"error": "internal_error", "message": "An unexpected error occurred.", "status_code": 500}
    assert "secret" not in r.text and "Traceback" not in r.text


# ---- rate limiting & caching ------------------------------------------------

def test_rate_limit_rejects_excess_requests(make_client):
    c = make_client(rate_limit_requests=3, rate_limit_window_seconds=60)
    assert [c.get(ITEM).status_code for _ in range(3)] == [200, 200, 200]
    r = c.get(ITEM)
    assert r.status_code == 429
    assert r.json()["error"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    assert c.get("/health").status_code == 200  # health is exempt


def test_cache_avoids_repeat_upstream_requests(client, site):
    assert client.get(ITEM).status_code == 200
    assert client.get(ITEM).status_code == 200
    assert len(site.calls) == 1
    assert client.app.state.cache.hits == 1


def test_cache_can_be_disabled_via_ttl_zero(make_client, site):
    c = make_client(cache_ttl_seconds=0)
    c.get(ITEM)
    c.get(ITEM)
    assert len(site.calls) == 2


def test_errors_are_not_cached(client, site):
    site.fail_mode = "500"
    client.get(ITEM)
    site.fail_mode, site.calls = None, []
    assert client.get(ITEM).status_code == 200
