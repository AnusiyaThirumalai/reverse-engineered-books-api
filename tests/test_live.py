"""Opt-in smoke test against the REAL site: RUN_LIVE_TESTS=1 pytest -m live -v

Not part of the default run (the suite must be deterministic and must not
depend on a third-party site being up).
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="set RUN_LIVE_TESTS=1 to run"),
]


@pytest.fixture(scope="module")
def live():
    with TestClient(create_app()) as c:
        yield c


def test_live_list_and_item_and_search(live):
    response = live.get("/api/v1/items", params={"limit": 5})
    if response.status_code == 503 and response.json().get("error") == "upstream_unavailable":
        pytest.skip("target website is unreachable from this environment")
    assert response.status_code == 200, response.text
    listing = response.json()
    assert listing["total"] >= 1 and len(listing["results"]) == 5

    first = listing["results"][0]
    item = live.get(f"/api/v1/items/{first['id']}").json()
    assert item["title"] == first["title"] and item["price"] is not None

    found = live.get("/api/v1/search", params={"q": "attic"}).json()
    assert any("attic" in b["title"].lower() for b in found["results"])
    assert live.get("/api/v1/items/definitely-not-a-book_0").status_code == 404
