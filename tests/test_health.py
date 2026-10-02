def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_openapi_docs_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    paths = spec.json()["paths"]
    for p in ("/health", "/api/v1/search", "/api/v1/items", "/api/v1/items/{item_id}", "/api/v1/categories"):
        assert p in paths


def test_no_generic_fetch_endpoint(client):
    """SSRF guard: the API must not expose any 'fetch arbitrary URL' capability."""
    paths = client.get("/openapi.json").json()["paths"]
    assert not any("fetch" in p or "proxy" in p for p in paths)
    assert client.get("/fetch", params={"url": "https://example.com"}).status_code == 404


def test_every_response_has_request_id(client):
    assert client.get("/health").headers.get("x-request-id")
