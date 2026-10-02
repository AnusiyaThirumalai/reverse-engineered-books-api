def test_search_finds_title(client):
    r = client.get("/api/v1/search", params={"q": "attic"})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "attic" and body["total"] == 1
    assert body["results"][0]["id"] == "a-light-in-the-attic_1000"
    assert body["scanned_pages"] == 3 and body["partial"] is False


def test_search_is_case_insensitive_and_multi_word(client):
    assert client.get("/api/v1/search", params={"q": "ATTIC"}).json()["total"] == 1
    body = client.get("/api/v1/search", params={"q": "northern lights"}).json()
    assert body["total"] == 3  # all tokens must match


def test_search_no_results(client):
    body = client.get("/api/v1/search", params={"q": "zzzznotabook"}).json()
    assert body["total"] == 0 and body["results"] == []


def test_search_limit_truncates_results_not_total(client):
    body = client.get("/api/v1/search", params={"q": "the", "limit": 5}).json()
    assert len(body["results"]) == 5 and body["total"] == 45


def test_search_reports_partial_scan(make_client):
    body = make_client(search_max_pages=2).get("/api/v1/search", params={"q": "the"}).json()
    assert body["scanned_pages"] == 2 and body["partial"] is True and body["total"] == 40


def test_search_within_category(client):
    body = client.get("/api/v1/search", params={"q": "the", "category": "mystery_3"}).json()
    assert body["total"] == 15


def test_search_unknown_category_404(client):
    r = client.get("/api/v1/search", params={"q": "x", "category": "nope_99"})
    assert r.status_code == 404 and r.json()["error"] == "not_found"


def test_repeat_search_served_from_cache(client, site):
    client.get("/api/v1/search", params={"q": "attic"})
    n = len(site.calls)
    client.get("/api/v1/search", params={"q": "garden"})
    assert len(site.calls) == n  # no new upstream requests
