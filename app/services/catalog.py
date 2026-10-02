"""Catalog service: turns API-level questions into a few upstream page fetches.

This is where the gaps in the target site are bridged:
  * the site has no search endpoint a crawler can use -> we scan listing pages
    (bounded by SEARCH_MAX_PAGES) and filter titles ourselves;
  * the site paginates at a fixed 20/page -> we translate page/limit.
"""

from __future__ import annotations

from app.config import UPSTREAM_PAGE_SIZE, Settings
from app.errors import NotFoundError
from app.models.schemas import (
    Book,
    BookDetail,
    CategoriesResponse,
    ListResponse,
    SearchResponse,
)
from app.services.parser import ListingPage, WebsiteParser
from app.services.scraper import WebsiteClient
from app.utils.logging import get_logger

log = get_logger("catalog")


def listing_path(category: str | None, page: int) -> str:
    """Path of listing page ``page`` (1-based) for all books or one category."""
    if category is None:
        return "/index.html" if page == 1 else f"/catalogue/page-{page}.html"
    base = f"/catalogue/category/books/{category}"
    return f"{base}/index.html" if page == 1 else f"{base}/page-{page}.html"


class BookCatalogService:
    def __init__(self, client: WebsiteClient, parser: WebsiteParser, settings: Settings) -> None:
        self._client = client
        self._parser = parser
        self._settings = settings

    async def _listing(self, category: str | None, page: int) -> ListingPage:
        path = listing_path(category, page)
        html = await self._client.fetch_page(path)
        return self._parser.parse_listing(html, self._client.build_url(path))

    async def list_books(self, page: int, limit: int, category: str | None) -> ListResponse:
        try:
            first = await self._listing(category, 1)
        except NotFoundError:
            if category:
                raise NotFoundError(f"Category '{category}' does not exist.") from None
            raise
        total = first.total_results if first.total_results is not None else len(first.books)

        offset = (page - 1) * limit
        if offset >= total:
            return ListResponse(
                page=page, limit=limit, total=total, has_more=False, category=category, results=[]
            )

        first_site_page = offset // UPSTREAM_PAGE_SIZE + 1
        last_site_page = (offset + limit - 1) // UPSTREAM_PAGE_SIZE + 1
        books: list[Book] = []
        for site_page in range(first_site_page, last_site_page + 1):
            try:
                lp = first if site_page == 1 else await self._listing(category, site_page)
            except NotFoundError:
                break
            books.extend(lp.books)

        start = offset - (first_site_page - 1) * UPSTREAM_PAGE_SIZE
        results = books[start : start + limit]
        return ListResponse(
            page=page,
            limit=limit,
            total=total,
            has_more=offset + len(results) < total,
            category=category,
            results=results,
        )

    async def search(self, query: str, category: str | None, limit: int) -> SearchResponse:
        tokens = query.lower().split()
        matches: list[Book] = []
        scanned = 0
        partial = False

        for page in range(1, self._settings.search_max_pages + 1):
            try:
                lp = await self._listing(category, page)
            except NotFoundError:
                if page == 1 and category:
                    raise NotFoundError(f"Category '{category}' does not exist.") from None
                break
            scanned += 1
            matches.extend(b for b in lp.books if all(t in b.title.lower() for t in tokens))
            if not lp.has_next:
                break
            if page == self._settings.search_max_pages:
                partial = True

        log.info("search done", extra={"scanned_pages": scanned, "matches": len(matches)})
        return SearchResponse(
            query=query,
            total=len(matches),
            results=matches[:limit],
            scanned_pages=scanned,
            partial=partial,
        )

    async def get_book(self, book_id: str) -> BookDetail:
        path = f"/catalogue/{book_id}/index.html"
        try:
            html = await self._client.fetch_page(path)
        except NotFoundError:
            raise NotFoundError(f"Book '{book_id}' was not found.") from None
        return self._parser.parse_item(html, self._client.build_url(path))

    async def list_categories(self) -> CategoriesResponse:
        lp = await self._listing(None, 1)
        return CategoriesResponse(total=len(lp.category_links), results=lp.category_links)
