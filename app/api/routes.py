"""HTTP layer only: validation, dependencies, response documentation.

No scraping or parsing here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request

from app.errors import BadRequestError, RateLimitedError
from app.models.schemas import (
    BookDetail,
    CategoriesResponse,
    ErrorResponse,
    ListResponse,
    SearchResponse,
)
from app.services.catalog import BookCatalogService

CATEGORY_PATTERN = r"^[a-z0-9-]{1,60}_\d{1,3}$"
ITEM_ID_PATTERN = r"^[A-Za-z0-9_-]{1,150}_\d+$"


def get_catalog(request: Request) -> BookCatalogService:
    return request.app.state.catalog


async def enforce_rate_limit(request: Request) -> None:
    """Per-client inbound limit. Keyed on the socket peer (X-Forwarded-For is
    not trusted: it is client-controlled unless set by a known proxy)."""
    client_key = request.client.host if request.client else "unknown"
    allowed, retry_after = request.app.state.limiter.check(client_key)
    if not allowed:
        wait = max(1, int(retry_after) + 1)
        raise RateLimitedError(
            f"Rate limit exceeded. Retry in about {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )


router = APIRouter(prefix="/api/v1", dependencies=[Depends(enforce_rate_limit)])

_ERRORS = {
    400: {"model": ErrorResponse, "description": "Invalid request parameters."},
    429: {"model": ErrorResponse, "description": "Too many requests (see Retry-After)."},
    500: {"model": ErrorResponse, "description": "Unexpected internal error."},
    502: {"model": ErrorResponse, "description": "Target website returned an unusable response."},
    503: {"model": ErrorResponse, "description": "Target website temporarily unavailable."},
}
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Resource does not exist."}}

CategoryParam = Query(
    None,
    pattern=CATEGORY_PATTERN,
    description="Category id from `/api/v1/categories`, e.g. `poetry_23`.",
    examples=["poetry_23"],
)


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search books by title",
    description=(
        "Case-insensitive title search. The source site exposes no crawlable search, "
        "so this scans up to `SEARCH_MAX_PAGES` listing pages (20 books each) and "
        "filters locally. Check `partial` to know whether the scan was cut short."
    ),
    responses={**_ERRORS, **_NOT_FOUND},
)
async def search(
    q: str = Query(..., min_length=1, max_length=100, description="Words that must all appear in the title.", examples=["light"]),
    category: str | None = CategoryParam,
    limit: int = Query(20, ge=1, le=100, description="Max results returned."),
    catalog: BookCatalogService = Depends(get_catalog),
) -> SearchResponse:
    query = " ".join(q.split())
    if not query:
        raise BadRequestError("Query must not be blank.")
    return await catalog.search(query, category, limit)


@router.get(
    "/items",
    response_model=ListResponse,
    summary="List books (paginated)",
    description="Paginated listing, optionally filtered by category. Max `limit` is 20 "
    "because the source site renders 20 books per page.",
    responses={**_ERRORS, **_NOT_FOUND},
)
async def list_items(
    page: int = Query(1, ge=1, le=10_000, description="1-based page number."),
    limit: int = Query(20, ge=1, le=20, description="Items per page (max 20)."),
    category: str | None = CategoryParam,
    catalog: BookCatalogService = Depends(get_catalog),
) -> ListResponse:
    return await catalog.list_books(page, limit, category)


@router.get(
    "/items/{item_id}",
    response_model=BookDetail,
    summary="Get one book",
    responses={**_ERRORS, **_NOT_FOUND},
)
async def get_item(
    item_id: str = Path(
        ..., pattern=ITEM_ID_PATTERN, description="Book id (URL slug).", examples=["a-light-in-the-attic_1000"]
    ),
    catalog: BookCatalogService = Depends(get_catalog),
) -> BookDetail:
    return await catalog.get_book(item_id)


@router.get(
    "/categories",
    response_model=CategoriesResponse,
    summary="List categories",
    responses=_ERRORS,
)
async def list_categories(catalog: BookCatalogService = Depends(get_catalog)) -> CategoriesResponse:
    return await catalog.list_categories()
