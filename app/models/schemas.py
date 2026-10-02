"""Public API contract (Pydantic models). Independent of the website's HTML."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_EXAMPLE_BOOK = {
    "id": "a-light-in-the-attic_1000",
    "title": "A Light in the Attic",
    "price": 51.77,
    "currency": "GBP",
    "rating": 3,
    "in_stock": True,
    "url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
    "image_url": "https://books.toscrape.com/media/cache/fe/72/example.jpg",
}


class Book(BaseModel):
    """Summary of a book as shown on listing pages."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_BOOK]})

    id: str = Field(description="Stable identifier: the URL slug on the source site.")
    title: str
    price: float | None = Field(None, description="Displayed price as a number.")
    currency: str | None = Field(None, description="ISO currency code (GBP for this source).")
    rating: int | None = Field(None, ge=1, le=5, description="Star rating 1-5, if present.")
    in_stock: bool | None = None
    url: str = Field(description="Canonical public page on the source site.")
    image_url: str | None = None


class BookDetail(Book):
    """Full book record from the product page."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    **_EXAMPLE_BOOK,
                    "category": "Poetry",
                    "description": "A collection of poems and drawings...",
                    "upc": "a897fe39b1053632",
                    "price_excl_tax": 51.77,
                    "price_incl_tax": 51.77,
                    "tax": 0.0,
                    "availability_text": "In stock (22 available)",
                    "stock_count": 22,
                    "number_of_reviews": 0,
                }
            ]
        }
    )

    category: str | None = None
    description: str | None = Field(None, description="Absent on some books at the source.")
    upc: str | None = None
    price_excl_tax: float | None = None
    price_incl_tax: float | None = None
    tax: float | None = None
    availability_text: str | None = None
    stock_count: int | None = None
    number_of_reviews: int | None = None


class Category(BaseModel):
    id: str = Field(description="Category slug, e.g. 'poetry_23'. Usable as the `category` filter.")
    name: str


class CategoriesResponse(BaseModel):
    total: int
    results: list[Category]


class ListResponse(BaseModel):
    page: int
    limit: int
    total: int = Field(description="Total books matching the filter on the source site.")
    has_more: bool
    category: str | None = None
    results: list[Book]


class SearchResponse(BaseModel):
    query: str
    total: int = Field(description="Matches found within the scanned portion of the catalogue.")
    results: list[Book]
    scanned_pages: int = Field(description="Source listing pages inspected for this search.")
    partial: bool = Field(
        description="True if the scan stopped at the configured page cap, so more "
        "matches may exist beyond what was scanned."
    )


class HealthResponse(BaseModel):
    status: str = "ok"


class ErrorResponse(BaseModel):
    error: str = Field(description="Stable machine-readable error code.")
    message: str
    status_code: int
