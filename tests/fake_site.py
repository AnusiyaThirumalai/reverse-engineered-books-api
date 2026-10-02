"""A deterministic stand-in for books.toscrape.com used by tests and the offline demo.

It renders HTML with the SAME markup structure as the real site (listing pages,
category pages, product pages, 20 books per page, 404s for unknown paths), and
can inject failures. Titles other than the first are synthetic.
"""

from __future__ import annotations

import re

import httpx

PAGE_SIZE = 20
CATEGORIES = [("poetry_23", "Poetry"), ("mystery_3", "Mystery"), ("travel_2", "Travel")]
_WORDS = [
    "Silent Garden", "Winter Orchard", "Paper Lanterns", "Distant Harbor", "Copper Sky",
    "Hidden Library", "Last Lighthouse", "Quiet River", "Golden Hour", "Midnight Train",
    "Salt and Stone", "Northern Lights", "Velvet Hours", "Broken Compass", "Open Window",
]


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def build_books(n: int = 45) -> list[dict]:
    books = []
    for i in range(n):
        title = "A Light in the Attic" if i == 0 else f"The {_WORDS[i % len(_WORDS)]} {i}"
        cat_id, cat_name = CATEGORIES[i % len(CATEGORIES)]
        books.append(
            {
                "id": f"{_slug(title)}_{1000 - i}",
                "title": title,
                "price": round(10 + i * 0.97, 2),
                "rating": ["One", "Two", "Three", "Four", "Five"][i % 5],
                "stock": i % 7 + 1,
                "category_id": cat_id,
                "category": cat_name,
            }
        )
    return books


def _listing_html(books: list[dict], page: int, pages: int, total: int, depth: str) -> str:
    cards = "".join(
        f"""<li><article class="product_pod">
<div class="image_container"><a href="{depth}{b['id']}/index.html"><img src="{'../' * (1 if depth == '' else 0)}media/cache/{b['id']}.jpg" alt=""></a></div>
<p class="star-rating {b['rating']}"></p>
<h3><a href="{depth}{b['id']}/index.html" title="{b['title']}">{b['title'][:15]}...</a></h3>
<div class="product_price"><p class="price_color">£{b['price']:.2f}</p><p class="instock availability">In stock</p></div>
</article></li>"""
        for b in books
    )
    nxt = '<li class="next"><a href="page-2.html">next</a></li>' if page < pages else ""
    cats = "".join(
        f'<li><a href="catalogue/category/books/{cid}/index.html"> {name} </a></li>'
        for cid, name in CATEGORIES
    )
    return f"""<html><head><title>Listing</title></head><body>
<div class="side_categories"><ul><li><a href="x">Books</a><ul>{cats}</ul></li></ul></div>
<div class="page-header action"><h1>Books</h1></div>
<form class="form-horizontal"><div><strong>{total}</strong> results - showing <strong>{(page-1)*PAGE_SIZE+1}</strong> to <strong>{(page-1)*PAGE_SIZE+len(books)}</strong>.</div></form>
<ol class="row">{cards}</ol><ul class="pager">{nxt}</ul></body></html>"""


def _item_html(b: dict) -> str:
    return f"""<html><body>
<ul class="breadcrumb"><li>Home</li><li>Books</li><li>{b['category']}</li><li class="active">{b['title']}</li></ul>
<article class="product_page">
<div id="product_gallery"><div class="item active"><img src="../../media/cache/{b['id']}.jpg"></div></div>
<div class="product_main"><h1>{b['title']}</h1><p class="price_color">£{b['price']:.2f}</p>
<p class="instock availability">In stock ({b['stock']} available)</p><p class="star-rating {b['rating']}"></p></div>
<div id="product_description"><h2>Product Description</h2></div><p>Synthetic description for {b['title']}.</p>
<table class="table table-striped">
<tr><th>UPC</th><td>upc{b['id'][-4:]}</td></tr>
<tr><th>Price (excl. tax)</th><td>£{b['price']:.2f}</td></tr><tr><th>Price (incl. tax)</th><td>£{b['price']:.2f}</td></tr>
<tr><th>Tax</th><td>£0.00</td></tr><tr><th>Availability</th><td>In stock ({b['stock']} available)</td></tr>
<tr><th>Number of reviews</th><td>0</td></tr></table></article></body></html>"""


class FakeSite:
    """Routes requests like the real site; ``fail_mode`` injects problems.

    fail_mode: None | "timeout" | "connect" | "500" | "503" | "403" | "malformed" | "empty" | "text"
    ``fail_first`` makes only the first N requests fail (to test retry recovery).
    """

    def __init__(self, n_books: int = 45) -> None:
        self.books = build_books(n_books)
        self.fail_mode: str | None = None
        self.fail_first: int | None = None
        self.calls: list[str] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)
        if self.fail_mode and (self.fail_first is None or len(self.calls) <= self.fail_first):
            return self._fail(request)
        return self._route(path)

    def _fail(self, request: httpx.Request) -> httpx.Response:
        mode = self.fail_mode
        if mode == "timeout":
            raise httpx.ReadTimeout("simulated timeout", request=request)
        if mode == "connect":
            raise httpx.ConnectError("simulated connection failure", request=request)
        if mode in {"500", "503", "403"}:
            return httpx.Response(int(mode), text="upstream failure")
        if mode == "malformed":
            return self._html("<html><body><h1>Maintenance</h1></body></html>")
        if mode == "empty":
            return self._html("")
        if mode == "text":
            return httpx.Response(200, text="plain", headers={"content-type": "text/plain"})
        raise AssertionError(f"unknown fail_mode {mode}")

    @staticmethod
    def _html(body: str) -> httpx.Response:
        # No charset on purpose: mirrors the real site, which sends none.
        return httpx.Response(200, content=body.encode("utf-8"), headers={"content-type": "text/html"})

    def _paged(self, books: list[dict], page: int, depth: str) -> httpx.Response:
        pages = max(1, -(-len(books) // PAGE_SIZE))
        if page < 1 or page > pages:
            return httpx.Response(404, text="not found")
        chunk = books[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        return self._html(_listing_html(chunk, page, pages, len(books), depth))

    def _route(self, path: str) -> httpx.Response:
        if path in ("/", "/index.html"):
            return self._paged(self.books, 1, "catalogue/")
        if m := re.fullmatch(r"/catalogue/page-(\d+)\.html", path):
            return self._paged(self.books, int(m.group(1)), "")
        if m := re.fullmatch(r"/catalogue/category/books/([a-z0-9-]+_\d+)/(index|page-(\d+))\.html", path):
            subset = [b for b in self.books if b["category_id"] == m.group(1)]
            if not subset:
                return httpx.Response(404, text="not found")
            return self._paged(subset, int(m.group(3) or 1), "../../../")
        if m := re.fullmatch(r"/catalogue/([A-Za-z0-9_-]+_\d+)/index\.html", path):
            for b in self.books:
                if b["id"] == m.group(1):
                    return self._html(_item_html(b))
        return httpx.Response(404, text="not found")
