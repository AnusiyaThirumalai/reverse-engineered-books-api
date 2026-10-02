"""HTML -> normalized models.

Everything website-specific lives in SELECTORS and the small helpers below.
These selectors are tied to the CURRENT markup of books.toscrape.com; if the
site changes its HTML, this is the only file that should need to change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.errors import ParseError
from app.models.schemas import Book, BookDetail, Category
from app.utils.logging import get_logger

log = get_logger("parser")

SELECTORS = {
    # listing pages (home, category, catalogue/page-N)
    "card": "article.product_pod",
    "card_link": "h3 a",
    "card_price": "p.price_color",
    "card_availability": "p.availability",
    "card_rating": "p.star-rating",
    "card_image": "div.image_container img",
    "listing_marker": "div.page-header, form.form-horizontal",  # proves it's a listing page
    "listing_total": "form.form-horizontal strong",
    "listing_next": "li.next a",
    "category_links": "div.side_categories ul li ul li a",
    # product page
    "item_root": "article.product_page",
    "item_title": "div.product_main h1",
    "item_price": "div.product_main p.price_color",
    "item_availability": "div.product_main p.availability",
    "item_rating": "div.product_main p.star-rating",
    "item_breadcrumb": "ul.breadcrumb li",
    "item_description": "#product_description + p",
    "item_image": "#product_gallery img",
    "item_table_rows": "table.table-striped tr",
}

_ID_RE = re.compile(r"([A-Za-z0-9_-]+_\d+)/index\.html$")
_CATEGORY_RE = re.compile(r"/category/books/([a-z0-9-]+_\d+)/index\.html$")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_STOCK_RE = re.compile(r"\((\d+)\s+available\)", re.I)
_RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


@dataclass
class ListingPage:
    books: list[Book]
    has_next: bool
    total_results: int | None = None
    category_links: list[Category] = field(default_factory=list)


def _clean(text: str | None) -> str | None:
    """Collapse whitespace; return None for empty."""
    if text is None:
        return None
    cleaned = " ".join(text.split())
    return cleaned or None


def _price(text: str | None) -> tuple[float | None, str | None]:
    """'£51.77' (or mojibake 'Â£51.77') -> (51.77, 'GBP')."""
    if not text:
        return None, None
    match = _NUMBER_RE.search(text)
    value = float(match.group()) if match else None
    currency = "GBP" if "£" in text else None
    return value, currency


def _rating(tag: Tag | None) -> int | None:
    if tag is None:
        return None
    for cls in tag.get("class", []):
        if cls in _RATING_WORDS:
            return _RATING_WORDS[cls]
    return None


def _in_stock(text: str | None) -> bool | None:
    if not text:
        return None
    return "in stock" in text.lower()


def _abs(base_url: str, ref: str | None) -> str | None:
    return urljoin(base_url, ref) if ref else None


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


class WebsiteParser:
    """Stateless parser for the target site."""

    def parse_listing(self, html: str, page_url: str) -> ListingPage:
        soup = _soup(html)
        cards = soup.select(SELECTORS["card"])
        if not cards and soup.select_one(SELECTORS["listing_marker"]) is None:
            raise ParseError("Unexpected page structure: not a recognizable listing page.")

        books: list[Book] = []
        for card in cards:
            book = self._parse_card(card, page_url)
            if book is not None:
                books.append(book)
        if cards and not books:
            raise ParseError("Listing cards found but none could be parsed.")

        total_tag = soup.select_one(SELECTORS["listing_total"])
        total = None
        if total_tag is not None:
            digits = re.sub(r"\D", "", total_tag.get_text())
            total = int(digits) if digits else None

        categories = []
        for a in soup.select(SELECTORS["category_links"]):
            m = _CATEGORY_RE.search(a.get("href", ""))
            name = _clean(a.get_text())
            if m and name:
                categories.append(Category(id=m.group(1), name=name))

        return ListingPage(
            books=books,
            has_next=soup.select_one(SELECTORS["listing_next"]) is not None,
            total_results=total,
            category_links=categories,
        )

    def parse_item(self, html: str, page_url: str) -> BookDetail:
        soup = _soup(html)
        root = soup.select_one(SELECTORS["item_root"])
        title_tag = soup.select_one(SELECTORS["item_title"])
        if root is None or title_tag is None or not _clean(title_tag.get_text()):
            raise ParseError("Unexpected page structure: not a recognizable product page.")

        m = _ID_RE.search(urlparse(page_url).path)
        if m is None:
            raise ParseError("Could not derive item id from product URL.")

        table: dict[str, str] = {}
        for row in soup.select(SELECTORS["item_table_rows"]):
            th, td = row.find("th"), row.find("td")
            if th and td:
                key, val = _clean(th.get_text()), _clean(td.get_text())
                if key and val:
                    table[key.lower()] = val

        price_tag = soup.select_one(SELECTORS["item_price"])
        price, currency = _price(price_tag.get_text() if price_tag else table.get("price (incl. tax)"))
        avail_tag = soup.select_one(SELECTORS["item_availability"])
        availability = _clean(avail_tag.get_text()) if avail_tag else table.get("availability")
        stock_match = _STOCK_RE.search(availability or "")

        crumbs = [_clean(li.get_text()) for li in soup.select(SELECTORS["item_breadcrumb"])]
        category = crumbs[-2] if len(crumbs) >= 3 else None  # Home > Books > <Category> > <Title>

        desc_tag = soup.select_one(SELECTORS["item_description"])
        img = soup.select_one(SELECTORS["item_image"])

        def money(key: str) -> float | None:
            return _price(table.get(key))[0]

        reviews = table.get("number of reviews")
        return BookDetail(
            id=m.group(1),
            title=_clean(title_tag.get_text()),  # type: ignore[arg-type]
            price=price,
            currency=currency,
            rating=_rating(soup.select_one(SELECTORS["item_rating"])),
            in_stock=_in_stock(availability),
            url=page_url,
            image_url=_abs(page_url, img.get("src") if img else None),
            category=category,
            description=_clean(desc_tag.get_text()) if desc_tag else None,
            upc=table.get("upc"),
            price_excl_tax=money("price (excl. tax)"),
            price_incl_tax=money("price (incl. tax)"),
            tax=money("tax"),
            availability_text=availability,
            stock_count=int(stock_match.group(1)) if stock_match else None,
            number_of_reviews=int(reviews) if reviews and reviews.isdigit() else None,
        )

    def _parse_card(self, card: Tag, page_url: str) -> Book | None:
        link = card.select_one(SELECTORS["card_link"])
        href = link.get("href") if link else None
        title = _clean((link.get("title") or link.get_text()) if link else None)
        id_match = _ID_RE.search(href or "")
        if not (link and href and title and id_match):
            log.warning("skipping listing card with missing link/title/id")
            return None

        price_tag = card.select_one(SELECTORS["card_price"])
        price, currency = _price(price_tag.get_text() if price_tag else None)
        avail = card.select_one(SELECTORS["card_availability"])
        img = card.select_one(SELECTORS["card_image"])
        return Book(
            id=id_match.group(1),
            title=title,
            price=price,
            currency=currency,
            rating=_rating(card.select_one(SELECTORS["card_rating"])),
            in_stock=_in_stock(avail.get_text() if avail else None),
            url=urljoin(page_url, href),
            image_url=_abs(page_url, img.get("src") if img else None),
        )
