def test_get_item(client, site):
    book = site.books[1]
    r = client.get(f"/api/v1/items/{book['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == book["id"] and body["title"] == book["title"]
    assert body["category"] == book["category"]
    assert body["price"] == book["price"] and body["currency"] == "GBP"
    assert body["stock_count"] == book["stock"]
    assert body["url"].startswith("https://books.toscrape.com/catalogue/")


def test_item_not_found(client):
    r = client.get("/api/v1/items/no-such-book_1")
    assert r.status_code == 404
    assert r.json() == {
        "error": "not_found",
        "message": "Book 'no-such-book_1' was not found.",
        "status_code": 404,
    }


def test_list_defaults(client, site):
    body = client.get("/api/v1/items").json()
    assert body["page"] == 1 and body["limit"] == 20 and body["total"] == 45
    assert body["has_more"] is True
    assert [b["id"] for b in body["results"]] == [b["id"] for b in site.books[:20]]


def test_list_last_page(client):
    body = client.get("/api/v1/items", params={"page": 3}).json()
    assert len(body["results"]) == 5 and body["has_more"] is False


def test_list_smaller_limit_within_one_site_page(client, site):
    body = client.get("/api/v1/items", params={"page": 2, "limit": 10}).json()
    assert [b["id"] for b in body["results"]] == [b["id"] for b in site.books[10:20]]


def test_list_page_spanning_two_site_pages(client, site):
    body = client.get("/api/v1/items", params={"page": 2, "limit": 15}).json()
    assert [b["id"] for b in body["results"]] == [b["id"] for b in site.books[15:30]]


def test_list_beyond_end_is_empty(client):
    body = client.get("/api/v1/items", params={"page": 99}).json()
    assert body["results"] == [] and body["has_more"] is False


def test_list_by_category(client):
    body = client.get("/api/v1/items", params={"category": "poetry_23"}).json()
    assert body["total"] == 15 and len(body["results"]) == 15 and body["category"] == "poetry_23"


def test_list_unknown_category(client):
    assert client.get("/api/v1/items", params={"category": "nope_99"}).status_code == 404


def test_categories(client):
    body = client.get("/api/v1/categories").json()
    assert body["total"] == 3
    assert {"id": "poetry_23", "name": "Poetry"} in body["results"]
