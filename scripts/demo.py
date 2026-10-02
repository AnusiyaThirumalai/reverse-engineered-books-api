#!/usr/bin/env python
"""End-to-end demo. Run one command, see the whole assignment work.

    python scripts/demo.py                  # against a running server (default http://localhost:8000)
    python scripts/demo.py --offline        # no network: in-process app on local HTML fixtures
    python scripts/demo.py --query poetry   # choose the search term

Exit code is 0 only if every step behaves as expected.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BAR = "=" * 44
failures: list[str] = []


def check(ok: bool, good: str, bad: str) -> bool:
    print(f"{'✓' if ok else '✗'} {good if ok else bad}")
    if not ok:
        failures.append(bad)
    return ok


def make_client(args: argparse.Namespace) -> httpx.Client:
    if args.offline:
        from fastapi.testclient import TestClient

        from app.config import Settings
        from app.main import create_app
        from tests.fake_site import FakeSite

        settings = Settings(upstream_min_interval_seconds=0, log_level="ERROR")
        print("(offline mode: local HTML fixtures, no network)\n")
        return TestClient(create_app(settings, transport=FakeSite().transport), base_url="http://demo")
    return httpx.Client(base_url=args.base_url, timeout=60)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--query", default="light")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    print(f"{BAR}\nReverse-Engineered API Demo\n{BAR}\n")
    try:
        with make_client(args) as c:
            run(c, args.query)
    except httpx.ConnectError:
        print(f"✗ Could not connect to {args.base_url}. Start the server first:\n"
              "    uvicorn app.main:app\n  or run with --offline.")
        return 2

    print(f"\n{BAR}")
    if failures:
        print(f"Demo FAILED ({len(failures)} problem(s))\n{BAR}")
        return 1
    print(f"Demo completed successfully\n{BAR}")
    return 0


def run(c: httpx.Client, query: str) -> None:
    print("[1] Health Check")
    r = c.get("/health")
    check(r.status_code == 200 and r.json() == {"status": "ok"}, "API is healthy", f"health returned {r.status_code}")

    print(f"\n[2] Search\nQuery: {query}")
    r = c.get("/api/v1/search", params={"q": query, "limit": 5})
    results = []
    if check(r.status_code == 200, "Search succeeded", f"search returned {r.status_code}: {r.text[:200]}"):
        body = r.json()
        results = body["results"]
        note = " (partial scan)" if body["partial"] else ""
        print(f"\nFound: {body['total']} results across {body['scanned_pages']} listing pages{note}")
        for b in results:
            price = f"£{b['price']:.2f}" if b["price"] is not None else "n/a"
            print(f"  - {b['title']}  [{b['id']}]  {price}")
        check(bool(results), "Results returned", f"no results for {query!r} - try --query")

    print("\n[3] Get Item")
    if results:
        pick = results[0]["id"]
        r = c.get(f"/api/v1/items/{pick}")
        if check(r.status_code == 200, f"Retrieved item: {r.json().get('title')}", f"item returned {r.status_code}"):
            d = r.json()
            print(f"    category={d['category']}  price={d['price']} {d['currency']}  "
                  f"rating={d['rating']}/5  stock={d['stock_count']}  upc={d['upc']}")
    else:
        check(False, "", "skipped: no item to retrieve")

    print("\n[4] Error Handling (invalid request)")
    r = c.get("/api/v1/items", params={"limit": 0})
    check(r.status_code == 400 and r.json().get("error") == "bad_request",
          f"Invalid request correctly handled -> 400 {r.json().get('error')}",
          f"expected 400, got {r.status_code}")
    print(f"    message: {r.json().get('message')}")

    print("\n[5] Not Found")
    r = c.get("/api/v1/items/no-such-book_0")
    check(r.status_code == 404 and r.json().get("error") == "not_found",
          f"404 correctly handled -> {r.json().get('message')}", f"expected 404, got {r.status_code}")


if __name__ == "__main__":
    raise SystemExit(main())
